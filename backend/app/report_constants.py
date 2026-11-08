CATEGORIES = {
    "pothole": {"en": "Pothole", "bn": "গর্ত (পথহোল)"},
    "damaged_road": {"en": "Damaged road", "bn": "ক্ষতিগ্রস্ত সড়ক"},
    "broken_sidewalk": {"en": "Broken sidewalk", "bn": "ভাঙা ফুটপাত"},
    "blocked_drainage": {"en": "Blocked drainage", "bn": "বন্ধ নর্দমা"},
    "waterlogging": {"en": "Waterlogging", "bn": "জলাবদ্ধতা"},
    "garbage": {"en": "Garbage accumulation", "bn": "আবর্জনা জমা"},
    "illegal_waste": {"en": "Illegal waste disposal", "bn": "অবৈধ বর্জ্য ফেলা"},
    "damaged_infrastructure": {"en": "Damaged public infrastructure", "bn": "ক্ষতিগ্রস্ত সরকারি অবকাঠামো"},
    "vegetation_loss": {"en": "Loss of vegetation", "bn": "সবুজ আচ্ছাদন হ্রাস"},
    "flooding": {"en": "Potential flooding area", "bn": "সম্ভাব্য বন্যাপ্রবণ এলাকা"},
    "other": {"en": "Other", "bn": "অন্যান্য"},
}

SEVERITIES = ("low", "medium", "high", "critical")

# Report status is not a verified issue. Phase 3 will add human verification.
REPORT_STATUSES = (
    "submitted",
    "acknowledged",
    "under_review",
    "insufficient_evidence",
    "resolved_unverified",
)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_FILES = 3
