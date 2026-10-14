from django.db import OperationalError
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from config.api import validated

from .serializers import SearchData, SearchInput
from .service import SearchUnavailable, search


class SearchThrottle(UserRateThrottle):
    rate = "30/minute"


class SearchView(APIView):
    throttle_classes = [SearchThrottle]

    @extend_schema(request=SearchInput, responses=SearchData)
    def post(self, request, workspace_id):
        data = validated(SearchInput, request)
        try:
            return Response(search(request.user, workspace_id, data))
        except OperationalError as error:
            raise SearchUnavailable() from error
