import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.template.loader import get_template
from django.utils import timezone, translation
from django.utils.translation import ugettext as _
from html2text import html2text

from mainapp.functions.mail import send_mail
from mainapp.functions.search_tools import MainappSearch, parse_hit
from mainapp.functions.search_notification_tools import search_result_for_notification
from mainapp.models import UserAlert


class Command(BaseCommand):
    help = "Notifies users about new search results"

    def perform_search(self, alert: UserAlert, override_since=None):
        if override_since is not None:
            since = override_since
        else:
            if alert.last_match is not None:
                since = alert.last_match
            else:
                since = timezone.now() - datetime.timedelta(days=14)

        params = alert.get_search_params()
        params["after"] = str(since)
        mainapp_search = MainappSearch(params)

        executed = mainapp_search.execute()
        results = [parse_hit(hit) for hit in executed.hits]

        return results

    def send_mail(self, to, message_text, message_html, pgp_key_fingerprint):
        send_mail(
            to, _("New search results"), message_text, message_html, pgp_key_fingerprint
        )

    def notify_user(self, user: User, override_since: datetime, debug: bool):
        context = {
            "base_url": settings.ABSOLUTE_URI_BASE,
            "site_name": settings.TEMPLATE_META["logo_name"],
            "alerts": [],
            "email": user.email,
        }

        for alert in user.useralert_set.all():
            notifyobjects = self.perform_search(alert, override_since)
            for obj in notifyobjects:
                search_result_for_notification(obj)

            if len(notifyobjects) > 0:
                results = []
                for obj in notifyobjects:
                    results.append(search_result_for_notification(obj))
                context["alerts"].append({"title": str(alert), "results": results})

        if debug:
            self.stdout.write(
                "User %s: %i results\n" % (user.email, len(context["alerts"]))
            )

        if len(context["alerts"]) == 0:
            return

        message_html = get_template("email/user-alert.html").render(context)
        message_html = message_html.replace("&lt;mark&gt;", "<mark>").replace(
            "&lt;/mark&gt;", "</mark>"
        )
        message_text = html2text(message_html)

        if debug:
            self.stdout.write(message_text)
        else:
            self.stdout.write("Sending notification to: %s" % user.email)
            self.send_mail(user.email, message_text, message_html, user.profile)

        if not override_since:
            for alert in user.useralert_set.all():
                alert.last_match = timezone.now()
                alert.save()

    def add_arguments(self, parser):
        parser.add_argument("--override-since", type=str)
        parser.add_argument("--debug", action="store_true")

    def handle(self, *args, **options):
        from django.conf import settings

        translation.activate(settings.LANGUAGE_CODE)

        override_since = options["override_since"]
        if override_since is not None:
            override_since = datetime.datetime.strptime(override_since, "%Y-%m-%d")

        users = User.objects.all()
        for user in users:
            if user.is_active:
                self.notify_user(user, override_since, options["debug"])
