from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import os
import sys
import traceback
import logging

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="معالج الصور الاحترافي", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# تحميل rembg مرة واحدة عند بدء التشغيل
logger.info("⏳ جاري تحميل نموذج إزالة الخلفية...")
try:
    from rembg import remove, new_session
    from PIL import Image, ImageFilter, ImageOps, ImageEnhance
    
    # u2net نموذج متوازن بين الدقة والسرعة
    session = new_session("u2net")
    logger.info("✅ تم تحميل النموذج بنجاح!")
    REMBG_READY = True
except Exception as e:
    logger.error(f"❌ فشل تحميل rembg: {e}")
    REMBG_READY = False


def process_image(product_bytes: bytes, logo_bytes: bytes) -> bytes:
    """المعالجة الكاملة على السيرفر"""
    
    input_image = Image.open(io.BytesIO(product_bytes)).convert("RGBA")
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    
    # إزالة الخلفية
    if REMBG_READY:
        cutout = remove(input_image, session=session).convert("RGBA")
    else:
        cutout = input_image
    
    # خلفية بيضاء
    white_bg = Image.new("RGBA", cutout.size, (255, 255, 255, 255))
    combined = Image.alpha_composite(white_bg, cutout)
    
    # ظل احترافي
    shadow = cutout.copy().convert("L").filter(ImageFilter.GaussianBlur(12))
    shadow = ImageOps.colorize(shadow, black="black", white="white").convert("RGBA")
    shadow_bg = Image.new("RGBA", combined.size, (255, 255, 255, 0))
    shadow_bg.paste(shadow, (8, 15), shadow)
    
    final_image = Image.alpha_composite(shadow_bg, combined)
    
    # إضافة الشعار
    img_w, img_h = final_image.size
    logo_size = int(img_w * 0.1)
    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
    
    alpha = logo.split()[-1]
    alpha = ImageEnhance.Brightness(alpha).enhance(0.6)
    logo.putalpha(alpha)
    
    margin = int(img_w * 0.03)
    pos_x = img_w - logo.size[0] - margin
    pos_y = img_h - logo.size[1] - margin
    
    final_image.paste(logo, (pos_x, pos_y), logo)
    final_image = final_image.convert("RGB")
    
    img_bytes = io.BytesIO()
    final_image.save(img_bytes, format="PNG", optimize=True)
    img_bytes.seek(0)
    
    return img_bytes.getvalue()


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Image Processor API",
        "rembg_ready": REMBG_READY,
        "host": "alwaysdata"
    }


@app.get("/health")
async def health():
    import psutil
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return {
        "status": "healthy",
        "rembg": REMBG_READY,
        "memory_mb": memory.available // (1024 * 1024),
        "disk_gb": disk.free // (1024**3)
    }


@app.post("/process")
async def process_endpoint(
    product: UploadFile = File(...),
    logo: UploadFile = File(...)
):
    if not product.content_type.startswith("image/"):
        raise HTTPException(400, "الملف الأول يجب أن يكون صورة")
    if not logo.content_type.startswith("image/"):
        raise HTTPException(400, "الملف الثاني يجب أن يكون صورة")
    
    try:
        product_bytes = await product.read()
        logo_bytes = await logo.read()
        
        max_size = 10 * 1024 * 1024
        if len(product_bytes) > max_size:
            raise HTTPException(400, "حجم صورة المنتج كبير جداً")
        
        result = process_image(product_bytes, logo_bytes)
        
        return StreamingResponse(
            io.BytesIO(result),
            media_type="image/png"
        )
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        await product.close()
        await logo.close()


# ============ للتشغيل المحلي فقط ============
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)