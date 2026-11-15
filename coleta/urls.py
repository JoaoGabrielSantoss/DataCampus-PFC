from django.urls import path

from . import views

app_name = "coleta"

urlpatterns = [
    path("", views.registrar, name="coleta"),
    path("pendencias/", views.lista_pendencias, name="pendencias"),
    path("participacao/<int:id>/", views.participacao, name="participacao"),
    path("estudo/<int:id>/", views.painel_estudo, name="painel_estudo"),
]
