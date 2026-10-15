"""
Where the API lives. Everything about one person sits under their user id, so the URL says
whose data it is. The version is in the path so a v2 can run next to v1 later.
"""

API_V1 = "/api/v1"
USER = API_V1 + "/users/{user_id}"
