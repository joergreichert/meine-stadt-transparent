import mimetypes
import textwrap
from collections import defaultdict
from tempfile import NamedTemporaryFile
from typing import Type, Optional

import gi
import requests
from django.conf import settings
from django.utils.translation import ugettext as _

# noinspection PyPackageRequirements
from requests import HTTPError
from slugify.slugify import slugify

from importer.functions import normalize_body_name
from importer.oparl_helper import OParlHelper
from mainapp.functions.document_parsing import extract_locations, extract_persons
from mainapp.functions.geo_functions import geocode
from mainapp.functions.minio import minio_client, minio_file_bucket
from mainapp.models import (
    Body,
    LegislativeTerm,
    Paper,
    Meeting,
    Location,
    File,
    Person,
    AgendaItem,
    OrganizationMembership,
    Organization,
    DefaultFields,
)
from mainapp.models.consultation import Consultation
from mainapp.models.organization_type import OrganizationType
from mainapp.models.paper_type import PaperType

# noinspection PyPackageRequirements

gi.require_version("OParl", "0.4")
from gi.repository import OParl


class OParlObjects(OParlHelper):
    """ Methods for saving the oparl objects as database entries. """

    def __init__(self, options, resolver):
        super().__init__(options, resolver)

        # We need this here for the sternberg fixup
        self.client = None

        # mappings that could not be resolved because the target object
        # hasn't been imported yet
        self.meeting_person_queue = defaultdict(list)
        self.meeting_organization_queue = defaultdict(list)
        self.agenda_item_paper_queue = {}
        self.membership_queue = []
        self.consultation_meeting_queue = []
        self.consultation_paper_queue = []
        self.consultation_organization_queue = defaultdict(list)
        self.paper_organization_queue = []

        # Ensure the existence of the three predefined organization types
        group = settings.PARLIAMENTARY_GROUPS_TYPE
        OrganizationType.objects.get_or_create(id=group[0], defaults={"name": group[1]})

        committee = settings.COMMITTEE_TYPE
        OrganizationType.objects.get_or_create(
            id=committee[0], defaults={"name": committee[1]}
        )

        department = settings.DEPARTMENT_TYPE
        OrganizationType.objects.get_or_create(
            id=department[0], defaults={"name": department[1]}
        )

    def body(self, libobject: OParl.Body):
        return self.process_object(libobject, Body, self.body_core, self.body_embedded)

    def body_core(self, libobject: OParl.Body, body: Body):
        self.logger.info("Processing {}".format(libobject.get_id()))

        normalize_body_name(body)

    def body_embedded(self, libobject: OParl.Body, body: Body):
        changed = False
        terms = []
        for term in libobject.get_legislative_term():
            saved_term = self.term(term)
            if saved_term:
                terms.append(saved_term)
        changed = changed or not self.is_queryset_equal_list(
            body.legislative_terms, terms
        )
        body.legislative_terms.set(terms)
        location = self.location(libobject.get_location())
        if location and location.geometry:
            if location.geometry["type"] == "Point":
                changed = changed or body.center != location
                body.center = location
                body.outline = None
            elif location.geometry["type"] == "Polygon":
                changed = changed or body.outline != location
                body.center = None
                body.outline = location
            else:
                message = (
                    "Location object is of type {}, which is neither 'Point' nor 'Polygon'."
                    "Skipping this location.".format(location.geometry["type"])
                )
                self.errorlist.append(message)
        return changed

    def term(self, libobject: OParl.LegislativeTerm):
        if not libobject.get_start_date() or not libobject.get_end_date():
            self.logger.error("Term has no start or end date - skipping")
            return

        term, do_update = self.check_for_modification(libobject, LegislativeTerm)
        if not term or not do_update:
            return term

        self.logger.info("Processing {}".format(libobject.get_name()))

        term.start = self.glib_datetime_to_python_date(libobject.get_start_date())
        term.end = self.glib_datetime_to_python_date(libobject.get_end_date())

        term.save()

        return term

    def paper(self, libobject: OParl.Paper):
        return self.process_object(
            libobject, Paper, self.paper_core, self.paper_embedded
        )

    def paper_embedded(self, libobject, paper):
        changed = False
        files_with_none = [self.file(file) for file in libobject.get_auxiliary_file()]
        files_without_none = [file for file in files_with_none if file is not None]
        changed = changed or not self.is_queryset_equal_list(
            paper.files, files_without_none
        )
        paper.files.set(files_without_none)
        old_main_file = paper.main_file
        paper.main_file = self.file(libobject.get_main_file())
        changed = changed or old_main_file != paper.main_file
        for i in libobject.get_consultation():
            self.consultation(i)

        organizations = []
        for org_url in libobject.get_under_direction_of_url():
            organization = Organization.objects.filter(oparl_id=org_url).first()
            if organization:
                organizations.append(organization)
            else:
                self.paper_organization_queue.append((paper, org_url))
        changed = changed or not self.is_queryset_equal_list(
            paper.organizations, organizations
        )
        paper.organizations.set(organizations)
        return changed

    def paper_core(self, libobject, paper):
        self.logger.info("Processing Paper {}".format(libobject.get_id()))
        if libobject.get_paper_type():
            paper_type, _ = PaperType.objects.get_or_create(
                defaults={"paper_type": libobject.get_paper_type()}
            )
        else:
            paper_type = None
        paper.legal_date = self.glib_datetime_to_python_date(libobject.get_date())
        paper.sort_date = paper.created
        paper.reference_number = libobject.get_reference()
        paper.paper_type = paper_type

        self.call_custom_hook("sanitize_paper", paper)

    def organization(self, libobject: OParl.Organization):
        return self.process_object(
            libobject, Organization, self.organization_core, self.organization_embedded
        )

    def organization_without_embedded(self, libobject: OParl.Organization):
        return self.process_object(
            libobject, Organization, self.organization_core, lambda x, y: False
        )

    def organization_embedded(self, libobject, organization):
        for membership in libobject.get_membership():
            self.membership(organization, membership)
        return False

    def organization_core(self, libobject, organization):
        self.logger.info("Processing Organization {}".format(libobject.get_id()))
        type_id = self.organization_classification.get(
            libobject.get_organization_type()
        )
        if type_id:
            orgtype = OrganizationType.objects.get(id=type_id)
        else:
            orgtype, _ = OrganizationType.objects.get_or_create(
                name=libobject.get_organization_type()
            )
        organization.organization_type = orgtype
        organization.body = Body.by_oparl_id(libobject.get_body().get_id())
        organization.start = self.glib_datetime_or_date_to_python(
            libobject.get_start_date()
        )
        organization.end = self.glib_datetime_or_date_to_python(
            libobject.get_end_date()
        )

        self.call_custom_hook("sanitize_organization", organization)

    def meeting(self, libobject: OParl.Meeting):
        return self.process_object(
            libobject, Meeting, self.meeting_core, self.meeting_embedded
        )

    def meeting_embedded(self, libobject, meeting):
        changed = False
        auxiliary_files = []
        for oparlfile in libobject.get_auxiliary_file():
            djangofile = self.file(oparlfile)
            if djangofile:
                auxiliary_files.append(djangofile)
        changed = changed or not self.is_queryset_equal_list(
            meeting.auxiliary_files, auxiliary_files
        )
        meeting.auxiliary_files.set(auxiliary_files)
        persons = []
        for oparlperson in libobject.get_participant():
            djangoperson = Person.by_oparl_id(oparlperson.get_id())
            if djangoperson:
                persons.append(djangoperson)
            else:
                self.meeting_person_queue[libobject.get_id()].append(
                    oparlperson.get_id()
                )
        changed = changed or not self.is_queryset_equal_list(meeting.persons, persons)
        meeting.persons.set(persons)
        for index, oparlitem in enumerate(libobject.get_agenda_item()):
            self.agendaitem(oparlitem, index, meeting)

        organizations = []
        for organization_url in libobject.get_organization_url():
            djangoorganization = Organization.objects.filter(
                oparl_id=organization_url
            ).first()
            if djangoorganization:
                organizations.append(djangoorganization)
            else:
                self.meeting_organization_queue[meeting].append(organization_url)
        changed = changed or not self.is_queryset_equal_list(
            meeting.organizations, organizations
        )
        meeting.organizations.set(organizations)

        return changed

    def meeting_core(self, libobject: OParl.Meeting, meeting):
        self.logger.info("Processing Meeting {}".format(libobject.get_id()))
        meeting.start = self.glib_datetime_to_python(libobject.get_start())
        meeting.end = self.glib_datetime_to_python(libobject.get_end())
        meeting.location = self.location(libobject.get_location())
        meeting.invitation = self.file(libobject.get_invitation())
        meeting.verbatim_protocol = self.file(libobject.get_verbatim_protocol())
        meeting.results_protocol = self.file(libobject.get_results_protocol())
        meeting.cancelled = libobject.get_cancelled() or False

        self.call_custom_hook("sanitize_meeting", meeting)

    def location(self, libobject: OParl.Location):
        location, do_update = self.check_for_modification(
            libobject, Location, name_fixup=_("Unknown")
        )
        if not location or not do_update:
            return location

        self.logger.info("Processing Location {}".format(libobject.get_id()))

        location.oparl_id = libobject.get_id()
        location.description = libobject.get_description()
        location.is_official = self.official_geojson
        location.geometry = self.extract_geometry(libobject.get_geojson())

        location.streetAddress = libobject.get_street_address()
        location.room = libobject.get_room()
        location.postalCode = libobject.get_postal_code()
        location.locality = libobject.get_locality()

        # Try to guess a better name for the location
        if libobject.get_room():
            location.short_description = libobject.get_room()

        if not location.description:
            description = ""
            if libobject.get_room():
                description += libobject.get_room() + ", "
            if libobject.get_street_address():
                description += libobject.get_street_address() + ", "
            if libobject.get_locality():
                if libobject.get_postal_code():
                    description += libobject.get_postal_code() + " "
                description += libobject.get_locality()
            location.description = description

        # If a streetAddress is present, we try to find the exact location on the map
        if location.streetAddress:
            search_str = libobject.get_street_address() + ", "
            if libobject.get_locality():
                if libobject.get_postal_code():
                    search_str += libobject.get_postal_code() + " "
                    search_str += libobject.get_locality()
            else:
                search_str += settings.GEOEXTRACT_DEFAULT_CITY
            search_str += " " + settings.GEOEXTRACT_SEARCH_COUNTRY

            geodata = geocode(search_str)
            if geodata:
                location.geometry = {
                    "type": "Point",
                    "coordinates": [geodata["lng"], geodata["lat"]],
                }

        location.save()

        return location

    def agendaitem(self, libobject: OParl.AgendaItem, index, meeting):
        item, do_update = self.check_for_modification(libobject, AgendaItem)
        if not item or not do_update:
            return item

        item.key = libobject.get_number()
        if not item.key:
            item.key = "-"

        item.oparl_id = libobject.get_id()
        item.key = libobject.get_number()
        item.title = libobject.get_name()
        item.position = index
        item.public = libobject.get_public()
        item.result = libobject.get_result()
        item.resolution_text = libobject.get_resolution_text()
        item.start = libobject.get_start()
        item.end = libobject.get_end()
        item.meeting = meeting

        item = self.call_custom_hook("sanitize_agenda_item", item)

        item.save()

        item.resolution_file = self.file(libobject.get_resolution_file())
        if len(libobject.get_auxiliary_file()) > 0:
            item.auxiliary_files = [
                self.file(i) for i in libobject.get_auxiliary_file()
            ]
        item.consultation = self.consultation(libobject.get_consultation())

        item.save()

        return item

    def consultation(self, libobject: OParl.Consultation):
        consultation, do_update = self.check_for_modification(libobject, Consultation)
        if not consultation or not do_update:
            return consultation

        consultation.oparl_id = libobject.get_id()
        consultation.authoritative = libobject.get_authoritative()
        consultation.role = libobject.get_role()

        consultation = self.call_custom_hook("sanitize_consultation", consultation)

        consultation.save()

        if libobject.get_meeting():
            meeting = Meeting.objects.filter(
                oparl_id=libobject.get_meeting().get_id()
            ).first()
            if not meeting:
                self.consultation_meeting_queue.append(
                    (consultation, libobject.get_meeting().get_id())
                )
            else:
                consultation.meeting = meeting

        if libobject.get_paper():
            paper = Meeting.objects.filter(
                oparl_id=libobject.get_paper().get_id()
            ).first()
            if not paper:
                self.consultation_paper_queue.append(
                    (consultation, libobject.get_paper().get_id())
                )
            else:
                consultation.paper = paper

        orgas = []
        for org_url in libobject.get_organization_url():
            organization = Meeting.objects.filter(oparl_id=org_url).first()
            if not organization:
                self.consultation_organization_queue[consultation].append(org_url)
            else:
                orgas.append(organization)
        consultation.organizations.set(orgas)

        consultation.save()

        return consultation

    def download_file(
        self, file: File, url: str, libobject: OParl.File
    ) -> Optional[NamedTemporaryFile]:
        last_modified = self.glib_datetime_to_python(libobject.get_modified())

        if (
            file.filesize
            and file.filesize > 0
            and file.modified
            and last_modified
            and last_modified < file.modified
            and minio_client.has_object(minio_file_bucket, str(file.id))
        ):
            self.logger.info("Skipping cached download: {}".format(url))
            return

        self.logger.info("Downloading {}".format(url))

        response = requests.get(url, allow_redirects=True)

        try:
            response.raise_for_status()
        except HTTPError as e:
            self.logger.exception("Failed to download file {}: {}", file.id, e)
            return

        tmpfile = NamedTemporaryFile()
        content = response.content
        tmpfile.write(content)
        tmpfile.file.seek(0)
        file.filesize = len(content)

        minio_client.put_object(
            minio_file_bucket,
            str(file.id),
            tmpfile.file,
            file.filesize,
            content_type=file.mime_type,
        )
        return tmpfile

    def file(self, libobject: OParl.File):
        file, do_update = self.check_for_modification(libobject, File)
        if not file or not do_update:
            return file
        self.logger.info("Processing File {}".format(libobject.get_id()))

        if libobject.get_file_name():
            displayed_filename = libobject.get_file_name()
        elif libobject.get_name():
            extension = mimetypes.guess_extension("application/pdf") or ""
            length = self.filename_length_cutoff - len(extension)
            displayed_filename = slugify(libobject.get_name())[:length] + extension
        else:
            displayed_filename = slugify(libobject.get_access_url())[
                -self.filename_length_cutoff :
            ]

        parsed_text_before = file.parsed_text
        file_name_before = file.name

        file.oparl_id = libobject.get_id()
        file.name = libobject.get_name()
        file.displayed_filename = displayed_filename
        file.mime_type = libobject.get_mime_type() or "application/octet-stream"
        file.legal_date = self.glib_datetime_to_python_date(libobject.get_date())
        file.sort_date = file.created
        file.oparl_access_url = libobject.get_access_url()
        file.oparl_download_url = libobject.get_download_url()
        file.filesize = -1

        file.save_without_historical_record()  # Generates an id which need for downloading the file

        # If no text comes from the API, don't overwrite previously extracted PDF-content with an empty string
        if libobject.get_text():
            file.parsed_text = libobject.get_text()

        if self.download_files:
            url = libobject.get_download_url() or libobject.get_access_url()
            tmpfile = self.download_file(file, url, libobject)
            if tmpfile:
                file.parsed_text = self.extract_text_from_file(file, tmpfile.name)
                tmpfile.close()

        file = self.call_custom_hook("sanitize_file", file)

        if len(file.name) > 200:
            file.name = textwrap.wrap(file.name, 199)[0] + "\u2026"

        if file_name_before != file.name or parsed_text_before != file.parsed_text:
            # These two operations are rather CPU-intensive, so we only perform them if something relevant has changed
            self.logger.info(
                "Extracting locations from PDF for file {} ({})".format(file.id, file)
            )
            file.locations.set(extract_locations(file.parsed_text))
            file.mentioned_persons.set(
                extract_persons(file.name + "\n" + (file.parsed_text or "") + "\n")
            )

        file.save()

        return file

    def person(self, libobject: OParl.Person):
        return self.process_object(
            libobject, Person, self.person_core, self.person_embedded
        )

    def person_embedded(self, libobject, person):
        old_location = person.location
        person.location = self.location(libobject.get_location())
        return old_location != person.location

    def person_core(self, libobject, person):
        self.logger.info("Processing Person {}".format(libobject.get_id()))
        person.name = libobject.get_name()
        person.given_name = libobject.get_given_name()
        person.family_name = libobject.get_family_name()

        self.call_custom_hook("sanitize_person", person)

    def membership(self, organization, libobject: OParl.Membership):
        membership, do_update = self.check_for_modification(
            libobject, OrganizationMembership
        )
        if not membership or not do_update:
            return membership

        person = Person.objects_with_deleted.filter(
            oparl_id=libobject.get_person().get_id()
        ).first()
        if not person:
            self.membership_queue.append((organization, libobject))
            return None

        role = libobject.get_role()
        if not role:
            role = _("Unknown")

        membership.start = self.glib_datetime_to_python_date(libobject.get_start_date())
        membership.end = self.glib_datetime_to_python_date(libobject.get_end_date())
        membership.role = role
        membership.person = person
        membership.organization = organization

        membership.save()

        return membership

    def _add_organizations(self, queue, othermodel: Type[DefaultFields]):
        length = len(queue)
        self.logger.info(
            "Adding missing {} to {} {}".format(
                Organization.__name__, length, othermodel.__name__
            )
        )
        for base_object, associated_urls in queue.items():
            associated = []
            for url in associated_urls:
                org = Organization.objects_with_deleted.filter(oparl_id=url).first()
                if not org:
                    org = self.organization_without_embedded(self.client.parse_url(url))
                    org.save()
                associated.append(org)
            base_object.organizations.set(associated)
            base_object.save()

    def add_missing_associations(self):
        self.logger.info(
            "Adding {} missing meeting <-> persons associations".format(
                len(self.meeting_person_queue.items())
            )
        )
        for meeting_id, person_ids in self.meeting_person_queue.items():
            meeting = Meeting.by_oparl_id(meeting_id)
            meeting.persons = [
                Person.by_oparl_id(person_id) for person_id in person_ids
            ]
            meeting.save()

        self.logger.info(
            "Adding {} missing agenda item <-> paper associations".format(
                len(self.agenda_item_paper_queue.items())
            )
        )
        for item_id, paper_id in self.agenda_item_paper_queue.items():
            item = AgendaItem.objects_with_deleted.get(oparl_id=item_id)
            item.paper = Paper.objects_with_deleted.filter(oparl_id=paper_id).first()
            if not item.paper:
                message = "Missing Paper: {}, ({})".format(paper_id, item_id)
                self.errorlist.append(message)
            item.save()

        self.logger.info(
            "Adding {} missing memberships".format(len(self.membership_queue))
        )
        for organization, libobject in self.membership_queue:
            person = Person.objects_with_deleted.filter(
                oparl_id=libobject.get_person().get_id()
            ).first()
            if not person:
                self.logger.warn("The person {} is missing".format(libobject.get_id()))
                self.person(libobject.get_person())
            self.membership(organization, libobject)

        self.logger.info(
            "Adding {} missing paper to consultations".format(
                len(self.consultation_paper_queue)
            )
        )
        for consultation, paper in self.consultation_paper_queue:
            consultation.paper = Paper.objects_with_deleted.filter(
                oparl_id=paper
            ).first()
            consultation.save()

        self.logger.info(
            "Adding {} missing meetings to consultations".format(
                len(self.consultation_meeting_queue)
            )
        )
        for consultation, meeting in self.consultation_meeting_queue:
            consultation.meeting = Meeting.objects_with_deleted.filter(
                oparl_id=meeting
            ).first()
            consultation.save()

        self.logger.info(
            "Adding {} missing organizations to papers".format(
                len(self.paper_organization_queue)
            )
        )
        for paper, organization_url in self.paper_organization_queue:
            org = Organization.objects_with_deleted.filter(
                oparl_id=organization_url
            ).first()
            if not org:
                org = self.organization_without_embedded(
                    self.client.parse_url(organization_url)
                )
            paper.organizations.add(org)

        self._add_organizations(self.consultation_organization_queue, Consultation)
        self._add_organizations(self.meeting_organization_queue, Meeting)
