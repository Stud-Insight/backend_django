from django.contrib import admin

from .models import TERIndividualRanking, TERPeriod, TERRanking, TERSubject


@admin.register(TERPeriod)
class TERPeriodAdmin(admin.ModelAdmin):
    list_display = ["name", "academic_year", "status", "group_formation_start", "project_end"]
    list_filter = ["status", "academic_year"]
    search_fields = ["name"]
    ordering = ["-academic_year", "-created"]


@admin.register(TERSubject)
class TERSubjectAdmin(admin.ModelAdmin):
    list_display = ["title", "ter_period", "domain", "professor", "status"]
    list_filter = ["status", "domain", "ter_period"]
    search_fields = ["title", "description"]
    ordering = ["-created"]


@admin.register(TERRanking)
class TERRankingAdmin(admin.ModelAdmin):
    list_display = ["group", "subject", "rank"]
    list_filter = ["subject__ter_period"]
    ordering = ["group", "rank"]


@admin.register(TERIndividualRanking)
class TERIndividualRankingAdmin(admin.ModelAdmin):
    list_display = ["user", "group", "subject", "rank"]
    list_filter = ["subject__ter_period"]
    ordering = ["group", "user", "rank"]
