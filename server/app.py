import math
import csv
import io

from pathlib import Path
from uuid import uuid4
from ocr_service import recognize_plate

from datetime import datetime
from db import create_entry_record, find_active_record, finish_exit_record, init_db

from flask import Flask, jsonify, render_template, request, redirect, session, url_for, make_response


from plate_detector import detect_and_crop_plate


from db import (
    create_entry_record,
    find_active_record,
    finish_exit_record,
    get_space_status,
    init_db,
    init_settings,
    list_all_records,
    occupy_one_space,
    release_one_space,
    update_total_spaces,
    get_dashboard_stats,
    update_hourly_rate,
)



BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__, template_folder="../client")

app.secret_key = "parking-system-admin-secret"
ADMIN_PASSWORD = "123456"


def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def error_response(action: str, message: str, status_code: int = 400, **extra):
    payload = {
        "success": False,
        "action": action,
        "message": message,
    }
    payload.update(extra)
    return jsonify(payload), status_code


def save_uploaded_image():
    if "image" not in request.files:
        return None, error_response("upload", "未检测到图片字段 image")

    file = request.files["image"]

    if file.filename == "":
        return None, (jsonify({"success": False, "message": "请选择图片后再上传"}), 400)

    if not allowed_file(file.filename):
        return None, (
            jsonify({"success": False, "message": "仅支持 png、jpg、jpeg 格式图片"}),
            400,
        )

    ext = file.filename.rsplit(".", 1)[1].lower()
    save_name = f"{uuid4().hex}.{ext}"
    save_path = UPLOAD_DIR / save_name
    file.save(save_path)

    return {"saved_as": save_name, "saved_path": str(save_path)}, None

def calculate_fee(entry_time: datetime, exit_time: datetime):
    duration_minutes = math.ceil((exit_time - entry_time).total_seconds() / 60)
    if duration_minutes < 0:
        duration_minutes = 0

    hours = math.ceil(duration_minutes / 60) if duration_minutes > 0 else 1

    settings = get_space_status()
    hourly_rate = float(settings["hourly_rate"])
    fee = hours * hourly_rate

    return duration_minutes, float(fee)




@app.get("/")
def index():
    return render_template("index.html")

@app.get("/admin")
def admin_page():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login_page"))
    return render_template("admin.html")

@app.get("/admin-login")
def admin_login_page():
    if session.get("is_admin"):
        return redirect(url_for("admin_page"))
    return render_template("admin_login.html")

@app.post("/admin-login")
def admin_login():
    password = request.form.get("password", "").strip()

    if password == ADMIN_PASSWORD:
        session["is_admin"] = True
        return redirect(url_for("admin_page"))

    return render_template("admin_login.html", error="密码错误，请重试")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin_login_page"))


@app.post("/api/entry")
def vehicle_entry():
    saved_file, upload_error = save_uploaded_image()
    if upload_error:
        return upload_error

    try:
        plate_crop_path = detect_and_crop_plate(saved_file["saved_path"])
        plate_number = recognize_plate(plate_crop_path)
    except Exception as error:
        return error_response(
            "entry",
            f"OCR 初始化或识别失败: {error}",
            500,
            saved_as=saved_file["saved_as"],
        )


    active_record = find_active_record(plate_number)
    if active_record:
        return error_response(
            "entry",
            "该车辆已在场，不允许重复入场",
            400,
            plate_number=plate_number,
            saved_as=saved_file["saved_as"],
        )
    
    space_status = get_space_status()
    if space_status["available_spaces"] <= 0:
        return error_response(
            "entry",
            "停车场已满，禁止入场",
            400,
            plate_number=plate_number,
            saved_as=saved_file["saved_as"],
        )



    entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    create_entry_record(plate_number, entry_time)
    occupy_one_space()


    return jsonify(
        {
            "success": True,
            "action": "entry",
            "message": "入场成功",
            "plate_number": plate_number,
            "entry_time": entry_time,
            "saved_as": saved_file["saved_as"],
        }
    )



@app.post("/api/exit")
def vehicle_exit():
    saved_file, upload_error = save_uploaded_image()
    if upload_error:
        return upload_error

    try:
        plate_crop_path = detect_and_crop_plate(saved_file["saved_path"])
        plate_number = recognize_plate(plate_crop_path)
    except Exception as error:
        return jsonify(
            {
                "success": False,
                "action": "exit",
                "message": f"OCR 初始化或识别失败: {error}",
                "saved_as": saved_file["saved_as"],
            }
        ), 500

    active_record = find_active_record(plate_number)
    if not active_record:
        return error_response(
            "exit",
            "未查询到该车辆的入场记录，不能出场",
            400,
            plate_number=plate_number,
            saved_as=saved_file["saved_as"],
        )


    entry_time_dt = datetime.strptime(active_record["entry_time"], "%Y-%m-%d %H:%M:%S")
    exit_time_dt = datetime.now()
    duration_minutes, fee = calculate_fee(entry_time_dt, exit_time_dt)
    exit_time_str = exit_time_dt.strftime("%Y-%m-%d %H:%M:%S")

    finish_exit_record(active_record["id"], exit_time_str, duration_minutes, fee)
    release_one_space()


    return jsonify(
        {
            "success": True,
            "action": "exit",
            "message": "出场成功",
            "plate_number": plate_number,
            "entry_time": active_record["entry_time"],
            "exit_time": exit_time_str,
            "duration_minutes": duration_minutes,
            "fee": fee,
            "saved_as": saved_file["saved_as"],
        }
    )

@app.get("/api/records")
def get_records():
    if not require_admin():
        return error_response("admin", "未授权访问", 403)
    rows = list_all_records()

    records = []
    for row in rows:
        records.append(
            {
                "id": row["id"],
                "plate_number": row["plate_number"],
                "entry_time": row["entry_time"],
                "exit_time": row["exit_time"],
                "duration_minutes": row["duration_minutes"],
                "fee": row["fee"],
                "status": row["status"],
            }
        )

    return jsonify(
        {
            "success": True,
            "count": len(records),
            "records": records,
        }
    )

@app.get("/api/space-status")
def get_parking_space_status():
    row = get_space_status()
    occupied_spaces = row["total_spaces"] - row["available_spaces"]

    return jsonify(
        {
            "success": True,
            "total_spaces": row["total_spaces"],
            "available_spaces": row["available_spaces"],
            "occupied_spaces": occupied_spaces,
        }
    )

@app.post("/api/space-status")
def set_parking_space_status():
    if not require_admin():
        return error_response("admin", "未授权访问", 403)
    data = request.get_json(silent=True)
    if not data or "total_spaces" not in data:
        return error_response("space", "缺少 total_spaces 参数", 400)

    try:
        total_spaces = int(data["total_spaces"])
    except (TypeError, ValueError):
        return error_response("space", "total_spaces 必须是整数", 400)

    if total_spaces <= 0:
        return error_response("space", "total_spaces 必须大于 0", 400)

    update_total_spaces(total_spaces)
    row = get_space_status()

    return jsonify(
        {
            "success": True,
            "message": "车位总数更新成功",
            "total_spaces": row["total_spaces"],
            "available_spaces": row["available_spaces"],
            "occupied_spaces": row["total_spaces"] - row["available_spaces"],
        }
    )

@app.get("/api/dashboard")
def get_dashboard():
    if not require_admin():
        return error_response("admin", "未授权访问", 403)
    stats = get_dashboard_stats()
    space = get_space_status()

    return jsonify(
        {
            "success": True,
            "total_records": stats["total_records"],
            "cars_in_lot": stats["cars_in_lot"],
            "completed_exits": stats["completed_exits"],
            "total_revenue": stats["total_revenue"],
            "total_spaces": space["total_spaces"],
            "available_spaces": space["available_spaces"],
            "occupied_spaces": space["total_spaces"] - space["available_spaces"],
            "hourly_rate": space["hourly_rate"],

        }
    )

def require_admin():
    return session.get("is_admin") is True

@app.get("/api/export-records")
def export_records():
    if not require_admin():
        return error_response("admin", "未授权访问", 403)

    rows = list_all_records()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "id",
        "plate_number",
        "entry_time",
        "exit_time",
        "duration_minutes",
        "fee",
        "status",
    ])

    for row in rows:
        writer.writerow([
            row["id"],
            row["plate_number"],
            row["entry_time"],
            row["exit_time"],
            row["duration_minutes"],
            row["fee"],
            row["status"],
        ])

    csv_content = output.getvalue()
    output.close()

    response = make_response(csv_content)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=parking_records.csv"
    return response

@app.post("/api/fee-rate")
def set_fee_rate():
    if not require_admin():
        return error_response("admin", "未授权访问", 403)

    data = request.get_json(silent=True)
    if not data or "hourly_rate" not in data:
        return error_response("fee", "缺少 hourly_rate 参数", 400)

    try:
        hourly_rate = float(data["hourly_rate"])
    except (TypeError, ValueError):
        return error_response("fee", "hourly_rate 必须是数字", 400)

    if hourly_rate <= 0:
        return error_response("fee", "hourly_rate 必须大于 0", 400)

    update_hourly_rate(hourly_rate)
    settings = get_space_status()

    return jsonify(
        {
            "success": True,
            "message": "收费标准更新成功",
            "hourly_rate": settings["hourly_rate"],
        }
    )




if __name__ == "__main__":
    init_db()
    init_settings()
    app.run(host="0.0.0.0", port=8000, debug=True)
