import icalendar
from django.conf import settings
from django.test import Client
from django.test import TestCase


expected_meeting = """
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Open Source Ratsinformationssystem//
BEGIN:VEVENT
SUMMARY:Meeting with Remy
DTSTART;TZID=Europe/Berlin;VALUE=DATE-TIME:20170910T120000
DTEND;TZID=Europe/Berlin;VALUE=DATE-TIME:20170910T180000
UID:meeting-1@opensourceris.local
DESCRIPTION:Meeting with Remy Danton
LOCATION:The Captiol
END:VEVENT
END:VCALENDAR
""".strip().replace("\n", "\r\n")

expected_meeting_series = """
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Open Source Ratsinformationssystem//
BEGIN:VEVENT
SUMMARY:House Assembly 1
DTSTART;TZID=Europe/Berlin;VALUE=DATE-TIME:20170901T120000
DTEND;TZID=Europe/Berlin;VALUE=DATE-TIME:20170901T140000
UID:meeting-3@opensourceris.local
DESCRIPTION:House Assembly Meeting 1
END:VEVENT
BEGIN:VEVENT
SUMMARY:House Assembly 2
DTSTART;TZID=Europe/Berlin;VALUE=DATE-TIME:20170908T120000
DTEND;TZID=Europe/Berlin;VALUE=DATE-TIME:20170908T140000
UID:meeting-4@opensourceris.local
DESCRIPTION:House Assembly Meeting 2
END:VEVENT
BEGIN:VEVENT
SUMMARY:House Assembly 3
DTSTART;TZID=Europe/Berlin;VALUE=DATE-TIME:20170915T120000
DTEND;TZID=Europe/Berlin;VALUE=DATE-TIME:20170915T140000
UID:meeting-5@opensourceris.local
DESCRIPTION:House Assembly Meeting 3
END:VEVENT
BEGIN:VEVENT
SUMMARY:House Assembly 4
DTSTART;TZID=Europe/Berlin;VALUE=DATE-TIME:20170922T120000
DTEND;TZID=Europe/Berlin;VALUE=DATE-TIME:20170922T140000
UID:meeting-6@opensourceris.local
DESCRIPTION:House Assembly Meeting 4
END:VEVENT
BEGIN:VEVENT
SUMMARY:House Assembly 5
DTSTART;TZID=Europe/Berlin;VALUE=DATE-TIME:20170929T120000
DTEND;TZID=Europe/Berlin;VALUE=DATE-TIME:20170929T140000
UID:meeting-7@opensourceris.local
DESCRIPTION:House Assembly Meeting 5
END:VEVENT
END:VCALENDAR
""".strip().replace("\n", "\r\n")


class TestICal(TestCase):
    fixtures = ['initdata']
    c = Client()

    def test_meeting(self):
        reponse = self.c.get('/meeting/1/ical').content.decode('utf-8').strip()
        self.assertEqual(reponse, expected_meeting)

        event = icalendar.cal.Component.from_ical(reponse).subcomponents[0]
        self.assertEqual(event.get("dtstart").dt.tzinfo.zone, settings.TIME_ZONE)
        self.assertEqual(event.get("dtstart").dt.hour, 12)
        self.assertEqual(event.get("dtend").dt.tzinfo.zone, settings.TIME_ZONE)
        self.assertEqual(event.get("dtend").dt.hour, 18)

    def test_meeting_series(self):
        reponse = self.c.get('/committee/2/ical').content.decode('utf-8').strip()
        self.assertEqual(reponse, expected_meeting_series)
        self.assertEqual(len(icalendar.cal.Component.from_ical(reponse).subcomponents[0]), 5)
