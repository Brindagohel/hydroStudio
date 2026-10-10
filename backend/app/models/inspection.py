from enum import Enum


class InspectionStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    NO_PLATE = "NO_PLATE"
    FAILED = "FAILED"


def inspection_to_dict(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "videoName": doc["videoName"],
        "status": doc["status"],
        "progress": doc.get("progress", 0),
        "detectedPlate": doc.get("detectedPlate"),
        "rawText": doc.get("rawText"),
        "confidence": doc.get("confidence"),
        "detectionConfidence": doc.get("detectionConfidence"),
        "lowConfidence": doc.get("lowConfidence", False),
        "manuallyCorrected": doc.get("manuallyCorrected", False),
        "hasPlateImage": bool(doc.get("plateImage")),
        "assetId": doc.get("assetId"),
        "hydrotestStatus": doc.get("hydrotestStatus"),
        "message": doc.get("message"),
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }
