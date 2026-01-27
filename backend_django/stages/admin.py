from django.contrib import admin

from .models import StageFavorite, StageOffer, StagePeriod, StageRanking


@admin.register(StagePeriod)
class StagePeriodAdmin(admin.ModelAdmin):
    list_display = ["name", "academic_year", "status", "application_start", "internship_end"]
    list_filter = ["status", "academic_year"]
    search_fields = ["name"]
    ordering = ["-academic_year", "-created"]


@admin.register(StageOffer)
class StageOfferAdmin(admin.ModelAdmin):
    list_display = ["title", "company_name", "stage_period", "domain", "supervisor", "status"]
    list_filter = ["status", "domain", "stage_period"]
    search_fields = ["title", "company_name", "description"]
    ordering = ["-created"]


@admin.register(StageRanking)
class StageRankingAdmin(admin.ModelAdmin):
    list_display = ["student", "offer", "rank"]
    list_filter = ["offer__stage_period"]
    ordering = ["student", "rank"]


@admin.register(StageFavorite)
class StageFavoriteAdmin(admin.ModelAdmin):
    list_display = ["student", "offer"]
    list_filter = ["offer__stage_period"]
