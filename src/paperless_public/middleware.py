from django.conf import settings


class CsrfExemptPublicApiMiddleware:
    """
    Disables CSRF checks for /api/public/ endpoints.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/public/'):
            setattr(request, '_dont_enforce_csrf_checks', True)
        return self.get_response(request)