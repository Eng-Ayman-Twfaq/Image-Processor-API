from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from rembg import remove
from PIL import Image, ImageFilter, ImageOps, ImageEnhance
import io
import os

app = FastAPI()

# تحميل الشعار الثابت مرة واحدة (مهم لتقليل الضغط)
LOGO_PATH = "bayn.png"
logo_static = Image.open(LOGO_PATH).convert("RGBA")


@app.post("/process-image/")
async def process_image(product: UploadFile = File(...)):

    # قراءة صورة المنتج
    product_bytes = await product.read()
    input_image = Image.open(io.BytesIO(product_bytes)).convert("RGBA")

    # 🔥 تقليل الحجم لتفادي انهيار Render
    input_image = input_image.resize((800, 800))

    # إزالة الخلفية
    cutout = remove(input_image).convert("RGBA")

    # خلفية بيضاء
    white_bg = Image.new("RGBA", cutout.size, (255, 255, 255, 255))
    combined = Image.alpha_composite(white_bg, cutout)

    # ظل خفيف
    shadow = cutout.copy().convert("L").filter(ImageFilter.GaussianBlur(10))
    shadow = ImageOps.colorize(shadow, black="black", white="white").convert("RGBA")

    shadow_bg = Image.new("RGBA", combined.size, (255, 255, 255, 0))
    shadow_bg.paste(shadow, (5, 10), shadow)

    final_image = Image.alpha_composite(shadow_bg, combined)

    # =========================
    # 🧾 الشعار الثابت (bayn.png)
    # =========================

    logo = logo_static.copy()

    img_w, img_h = final_image.size

    logo_size = int(img_w * 0.12)
    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)

    # شفافية
    alpha = logo.split()[-1]
    alpha = ImageEnhance.Brightness(alpha).enhance(0.7)
    logo.putalpha(alpha)

    margin = int(img_w * 0.03)

    pos_x = img_w - logo.size[0] - margin
    pos_y = img_h - logo.size[1] - margin

    final_image.paste(logo, (pos_x, pos_y), logo)

    # =========================
    # إرجاع الصورة
    # =========================

    img_byte_arr = io.BytesIO()
    final_image.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)

    return StreamingResponse(img_byte_arr, media_type="image/png")