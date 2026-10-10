# YOLO model folder

Put the number plate detection weights here as `number_plate_model.pt`
(or point `YOLO_MODEL_PATH` in `backend/.env` to another file).

The weights are **not** committed: they are large and each model has its own
licence. Any Ultralytics YOLO model trained to detect licence plates works.
For example, train YOLOv8 on a public licence-plate dataset (Roboflow Universe,
Open Images) or download weights whose licence you have checked.

If the file is missing the API answers `503: Number plate detection model is not
configured.` - the rest of the application keeps working.
