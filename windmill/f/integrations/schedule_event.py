"""
Windmill script: schedule_event
Input: title, start_time, end_time, description (JSON body from agent-api)
Configure Google Calendar resource in Windmill; implement API call here.
"""


def main(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
):
    # TODO: bind wmill.get_resource("google_calendar") when OAuth configured
    return {
        "status": "accepted",
        "action": "schedule_event",
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "description": description,
    }
