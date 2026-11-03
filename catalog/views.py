from rest_framework.response import Response
from rest_framework.views import APIView

from . import repository


class ProductListView(APIView):
    def get(self, request):
        search = request.query_params.get("search", "").strip()
        return Response(repository.list_active(search))
