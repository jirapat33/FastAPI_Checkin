from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import gspread
import requests
import datetime
import json
import os

app = FastAPI()

# ปลดล็อก CORS ป้องกันหน้าเว็บโดนบล็อกการส่งข้อมูล
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 ใส่ API Key ของ ImgBB ที่คุณสมัครได้ที่นี่
# แก้ไขบรรทัด IMGBB_API_KEY ใน main.py บน GitHub ให้เป็นแบบนี้:
IMGBB_API_KEY = "c299dc524f2bc43c2d766741c0a83047"

class CheckInSchema(BaseModel):
    studentId: str
    lat: float
    lon: float
    image: str

@app.get("/", response_class=HTMLResponse)
async def read_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>ไฟล์ index.html ไม่โดนอัปโหลดเข้าเซิร์ฟเวอร์</h1>"

@app.post("/api/checkin")
async def process_check_in(data: CheckInSchema):
    try:
        # 1. อัปโหลดรูปภาพที่ถ่ายได้เข้าสู่ ImgBB Cloud Storage
        raw_image = data.image.split(",")[1] if "," in data.image else data.image
        imgbb_url = "https://api.imgbb.com/1/upload"
        
        res_image = requests.post(imgbb_url, data={
            "key": IMGBB_API_KEY,
            "image": raw_image
        }).json()
        
        if not res_image.get("success"):
            return {"status": "ERROR", "message": "ระบบเก็บรูปภาพปลายทางขัดข้อง ทำรายการไม่สำเร็จ"}
            
        photo_url = res_image["data"]["url"]

        # 2. 🔥 ดึงคีย์ยืนยันตัวตนจาก Environment Variables บน Render
        cred_env = os.environ.get("credentials.json")
        if not cred_env:
            return {"status": "ERROR", "message": "เซิร์ฟเวอร์หาค่ารหัสใน Environment Variables ไม่เจอ"}
            
        # แปลงข้อความ Text จากตัวแปรให้กลายเป็นโครงสร้าง JSON ดิบเพื่อเปิดสิทธิ์เข้าใช้ชีต
        info = json.loads(cred_env)
        gc = gspread.service_account_from_dict(info)
        
        sh = gc.open("เช็คชื่อฝึกงาน")  # ชื่อไฟล์ใน Google Sheets
        worksheet = sh.worksheet("ปวส2/1")

        # ดึงรายชื่อรหัสนักศึกษาในคอลัมน์ C มาทั้งหมด (ตัดแถวหัวตารางออก)
        student_ids = worksheet.col_values(3)[1:]
        input_id = data.studentId.strip()

        if input_id not in student_ids:
            return {"status": "ERROR", "message": f"ระบุรหัสผิด หรือไม่พบรหัสนักศึกษา [{input_id}] ในห้อง ปวส.2/1"}

        # หาแถวของนักศึกษาในระบบ (+2 เพื่อชดเชย index 0 และ แถวหัวข้อตาราง)
        target_row = student_ids.index(input_id) + 2

        # 3. บันทึกประวัติพิกัดและลิงก์ภาพลงล็อกของนักศึกษา
        # ตั้งเวลาปัจจุบันแบบเขตเวลาไทย (GMT+7)
        tz_offset = datetime.timezone(datetime.timedelta(hours=7))
        current_time = datetime.datetime.now(tz_offset).strftime("%Y-%m-%d %H:%M:%S")
        
        worksheet.update_cell(target_row, 1, current_time)  # คอลัมน์ A: วันที่-เวลา
        worksheet.update_cell(target_row, 5, data.lat)       # คอลัมน์ E: ละติจูด
        worksheet.update_cell(target_row, 6, data.lon)       # คอลัมน์ F: ลองจิจูด
        worksheet.update_cell(target_row, 7, photo_url)     # คอลัมน์ G: ลิงก์รูปถ่าย

        return {"status": "SUCCESS", "message": "เช็คอินสำเร็จและบันทึกพิกัดลง Google Sheets แล้ว!"}

    #  เปลี่ยนเป็นโค้ดชุดนี้แทน:
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
