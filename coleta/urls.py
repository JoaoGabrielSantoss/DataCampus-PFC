from django.urls import path

from . import views

app_name = "coleta"

urlpatterns = [
    path("", views.registrar, name="coleta"),
    path("area-voluntario/", views.area_voluntario, name="area_voluntario"),
    path("area-voluntario/perfil/", views.perfil_voluntario, name="perfil_voluntario"),
    path("area-voluntario/avaliar/<int:id>/", views.avaliar_participacao_voluntario, name="avaliar_voluntario"),
    path("area-voluntario/sair/", views.sair_area_voluntario, name="sair_voluntario"),
    path("avaliacoes/", views.avaliacoes_pesquisador, name="avaliacoes_pesquisador"),
    path("voluntarios/", views.lista_voluntarios, name="lista_voluntarios"),
    path("pendencias/", views.lista_pendencias, name="pendencias"),
    path("participacao/<int:id>/", views.participacao, name="participacao"),
    path("estudo/<int:id>/", views.painel_estudo, name="painel_estudo"),
]
