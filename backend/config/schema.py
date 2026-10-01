from drf_spectacular.authentication import SessionScheme


class BrowserSessionScheme(SessionScheme):
    target_class = "config.api.BrowserSessionAuthentication"
    priority = 1
