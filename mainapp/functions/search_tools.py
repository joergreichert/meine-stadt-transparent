import datetime
from typing import NamedTuple

from django.conf import settings
from django.urls import reverse
from django.utils.translation import ugettext as _
from elasticsearch_dsl import Search, Q

from meine_stadt_transparent.settings import ABSOLUTE_URI_BASE

QUERY_KEYS = ["document-type", "radius", "lat", "lng", "person", "after", "before"]


class NotificationSearchResult(NamedTuple):
    title: str
    url: str
    type: str
    type_name: str


def add_date(s, raw, operator, options, errors):
    """ Filters by a date given a string, catching parsing errors. """
    try:
        after = datetime.datetime.strptime(raw, '%Y-%m-%d')
        s = s.filter(Q('range', start={operator: after}) | Q('range', legal_date={operator: after}))
        options["after"] = after
    except ValueError or OverflowError:
        errors.append(_('The value for after is invalid. The correct format is YYYY-MM-DD'))
    return s


def add_modified_since(s, since: datetime):
    s = s.filter(Q('range', modified={'gte': since}))
    return s


def params_to_query(params: dict):
    s = Search(index=settings.ELASTICSEARCH_INDEX)
    options = {}
    errors = []
    if 'searchterm' in params and params['searchterm'] is not "":
        s = s.query('query_string', query=params['searchterm'])
        options['searchterm'] = params['searchterm']

    try:
        lat = float(params.get('lat', ''))
        lng = float(params.get('lng', ''))
        radius = int(params.get('radius', ''))
        s = s.filter("geo_distance", distance=str(radius) + "m", coordinates={
            "lat": lat,
            "lon": lng,
        })
        options['lat'] = str(lat)
        options['lng'] = str(lng)
        options['radius'] = str(radius)
    except ValueError:
        pass
    if 'document-type' in params:
        split = params['document-type'].split(",")
        s = s.filter('terms', _type=[i + "_document" for i in split])
        options["document_type"] = split
    if 'after' in params:
        s = add_date(s, params['after'], "gte", options, errors)
    if 'before' in params:
        s = add_date(s, params['before'], "lte", options, errors)

    return options, s, errors


def search_string_to_params(query: str):
    values = [value.strip() for value in query.split(" ")]
    keys = QUERY_KEYS
    params = dict()
    for value in values[:]:
        for key in keys:
            if value.startswith(key + ":"):
                values.remove(value)
                value = value[len(key + ":"):]
                params[key] = value
    if len(values) > 0:
        params["searchterm"] = " ".join(values).replace("  ", " ").strip()
    return params


def params_to_search_string(params: dict):
    values = []
    for key, value in sorted(params.items()):
        if key != "searchterm":
            values.append(key + ":" + value)
    if "searchterm" in params:
        values.append(params["searchterm"])
    searchstring = " ".join(values)
    return searchstring


def params_are_equal(params1: dict, params2: dict):
    return params_to_search_string(params1) == params_to_search_string(params2)


def params_are_subscribable(params: dict):
    if 'after' in params:
        return False
    if 'before' in params:
        return False
    return True


def search_result_for_notification(result):
    from mainapp.documents import DOCUMENT_TYPE_NAMES

    if result["type"] == "meeting":
        title = result["name"]
        url = ABSOLUTE_URI_BASE + reverse('meeting', args=[result["id"]])
    elif result["type"] == "paper":
        title = result["name"]
        url = ABSOLUTE_URI_BASE + reverse('paper', args=[result["id"]])
    elif result["type"] == "file": # displayed_filename?
        title = result["name"]
        url = ABSOLUTE_URI_BASE + reverse('file', args=[result["id"]])
    else:
        title = "Unknown"
        url = ""

    return NotificationSearchResult(
        title=title,
        url=url,
        type=result["type"],
        type_name=DOCUMENT_TYPE_NAMES[result["type"]]
    )
