from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from rembg import remove
from PIL import Image, ImageFilter, ImageOps, ImageEnhance
import io

app = FastAPI()


@app.post("/process-image/")
async def process_image(
    product: UploadFile = File(...),
    logo: UploadFile = File(...)
):

    # قراءة الملفات
    product_bytes = await product.read()
    logo_bytes = await logo.read()

    input_image = Image.open(io.BytesIO(product_bytes)).convert("RGBA")
    logo_img = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")

    # إزالة الخلفية
    cutout = remove(input_image).convert("RGBA")

    # خلفية بيضاء
    white_bg = Image.new("RGBA", cutout.size, (255, 255, 255, 255))
    combined = Image.alpha_composite(white_bg, cutout)

    # ظل احترافي
    shadow = cutout.copy().convert("L").filter(ImageFilter.GaussianBlur(12))
    shadow = ImageOps.colorize(shadow, black="black", white="white").convert("RGBA")

    shadow_bg = Image.new("RGBA", combined.size, (255, 255, 255, 0))
    shadow_bg.paste(shadow, (8, 15), shadow)

    final_image = Image.alpha_composite(shadow_bg, combined)

    # الشعار
    img_w, img_h = final_image.size
    logo_size = int(img_w * 0.1)

    logo_img.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)

    alpha = logo_img.split()[-1]
    alpha = ImageEnhance.Brightness(alpha).enhance(0.65)
    logo_img.putalpha(alpha)

    margin = int(img_w * 0.03)

    pos_x = img_w - logo_img.size[0] - margin
    pos_y = img_h - logo_img.size[1] - margin

    final_image.paste(logo_img, (pos_x, pos_y), logo_img)

    # تحويل الصورة للإرجاع
    img_byte_arr = io.BytesIO()
    final_image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    return StreamingResponse(img_byte_arr, media_type="image/png")