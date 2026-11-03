from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from . import repository
from .serializers import OrderCreateSerializer
from .services import create_order, delete_order, update_order


class OrderListCreateView(APIView):
    def get(self, request):
        """Orders grouped by local date (newest first) with a total per date."""
        return Response(repository.grouped_by_date())

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_order(**serializer.validated_data)
        return Response(repository.detail(order), status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    def get(self, request, pk):
        order = repository.get(pk)
        if order is None:
            raise NotFound()
        return Response(repository.detail(order))

    def put(self, request, pk):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = update_order(pk, **serializer.validated_data)
        if order is None:
            raise NotFound()
        return Response(repository.detail(order))

    def delete(self, request, pk):
        if delete_order(pk) is None:
            raise NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)
