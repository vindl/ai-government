"""Enums for government models."""

from enum import StrEnum


class MinistryType(StrEnum):
    """Identifiers for each ministry agent in the AI cabinet."""

    FINANCE = "finance"
    JUSTICE = "justice"
    EU = "eu"
    HEALTH = "health"
    INTERIOR = "interior"
    EDUCATION = "education"
    ECONOMY = "economy"
    TOURISM_ECOLOGY = "tourism"
    ENVIRONMENT = "environment"
    LABOUR = "labour"
