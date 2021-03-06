import json
from typing import Optional

import gi

from mainapp.models import File
from .oparl_import import OParlImport

gi.require_version("OParl", "0.4")
from gi.repository import OParl


class SternbergResolver:
    """ Class for patching up the failures in Sternberg OParl """

    def __init__(self, original_resolver):
        self.original_resolver = original_resolver

    def resolve(self, url: str):
        response = self.original_resolver.resolve(url)
        if not response.get_success():
            return response

        if "/body" in url:
            oparl_list = json.loads(response.get_resolved_data())

            # Add missing "type"-attributes in body-lists
            if "data" in oparl_list:
                for oparl_object in oparl_list["data"]:
                    if "location" in oparl_object.keys() and isinstance(
                        oparl_object["location"], dict
                    ):
                        oparl_object["location"][
                            "type"
                        ] = "https://schema.oparl.org/1.0/Location"

            # Add missing "type"-attributes in single bodies
            if "location" in oparl_list.keys() and isinstance(
                oparl_list["location"], dict
            ):
                oparl_list["location"]["type"] = "https://schema.oparl.org/1.0/Location"

            # Location in Person must be a url, not an object
            if "/person" in url and "data" in oparl_list:
                for oparl_object in oparl_list["data"]:
                    if "location" in oparl_object and isinstance(
                        oparl_object["location"], dict
                    ):
                        oparl_object["location"] = oparl_object["location"]["id"]

            if "/organization" in url and "data" in oparl_list:
                for oparl_object in oparl_list["data"]:
                    if "id" in oparl_object and "type" not in oparl_object:
                        oparl_object[
                            "type"
                        ] = "https://schema.oparl.org/1.0/Organization"

            response = OParl.ResolveUrlResult(
                resolved_data=json.dumps(oparl_list),
                success=True,
                status_code=response.get_status_code(),
            )

        if "/membership" in url:
            oparl_list = json.loads(response.get_resolved_data())

            # If an array is returned instead of an object, we just skip all list entries except for the last one
            if isinstance(oparl_list, list):
                oparl_list = oparl_list[0]

            response = OParl.ResolveUrlResult(
                resolved_data=json.dumps(oparl_list),
                success=True,
                status_code=response.get_status_code(),
            )

        if "/person" in url:
            oparl_object = json.loads(response.get_resolved_data())
            if "location" in oparl_object and not isinstance(
                oparl_object["location"], str
            ):
                oparl_object["location"] = oparl_object["location"]["id"]

            response = OParl.ResolveUrlResult(
                resolved_data=json.dumps(oparl_object),
                success=True,
                status_code=response.get_status_code(),
            )

        if "/meeting" in url:
            oparl_object = json.loads(response.get_resolved_data())
            if "location" in oparl_object and not isinstance(
                oparl_object["location"], str
            ):
                oparl_object["location"][
                    "type"
                ] = "https://schema.oparl.org/1.0/Location"

            response = OParl.ResolveUrlResult(
                resolved_data=json.dumps(oparl_object),
                success=True,
                status_code=response.get_status_code(),
            )

        return response


class SternbergImport(OParlImport):
    def __init__(self, options, resolver):
        sternberg_resolver = SternbergResolver(resolver)
        super().__init__(options, sternberg_resolver)

    def download_file(
        self, file: File, url: str, libobject: OParl.File
    ) -> Optional[bytes]:
        """ Fix the invalid urls of sternberg oparl """
        url = url.replace(r"files//rim", r"files/rim")
        return super().download_file(file, url, libobject)
