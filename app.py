from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from rembg import remove
from PIL import Image, ImageFilter, ImageOps, ImageEnhance
import io
import uvicorn

app = FastAPI(title="Image Processor API", version="1.0.0")

# السماح بالوصول من أي مصدر
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def process_image(product_bytes: bytes, logo_bytes: bytes) -> bytes:
    """معالجة الصورة وإرجاعها كـ bytes"""
    
    # فتح الصور
    input_image = Image.open(io.BytesIO(product_bytes)).convert("RGBA")
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    
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
    
    # تحويل إلى bytes
    img_bytes = io.BytesIO()
    final_image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    
    return img_bytes.getvalue()


@app.post("/process")
async def process_endpoint(
    product: UploadFile = File(..., description="صورة المنتج"),
    logo: UploadFile = File(..., description="صورة الشعار")
):
    """
    معالجة الصورة: إزالة الخلفية + ظل + إضافة شعار
    
    تُرسل الصورتين وتستقبل الصورة المعالجة مباشرة
    """
    # التحقق من نوع الملفات
    if not product.content_type.startswith("image/"):
        raise HTTPException(400, "الملف الأول يجب أن يكون صورة")
    if not logo.content_type.startswith("image/"):
        raise HTTPException(400, "الملف الثاني يجب أن يكون صورة")
    
    try:
        # قراءة الملفات
        product_bytes = await product.read()
        logo_bytes = await logo.read()
        
        # معالجة الصورة
        result = process_image(product_bytes, logo_bytes)
        
        # إرجاع الصورة
        return StreamingResponse(
            io.BytesIO(result),
            media_type="image/png",
            headers={"Content-Disposition": "inline; filename=result.png"}
        )
        
    except Exception as e:
        raise HTTPException(500, f"خطأ في المعالجة: {str(e)}")
    finally:
        await product.close()
        await logo.close()


@app.get("/")
async def root():
    """رسالة ترحيب بسيطة"""
    return {
        "message": "Image Processor API",
        "version": "1.0.0",
        "endpoint": "/process",
        "method": "POST",
        "usage": "أرسل صورتين: product و logo"
    }


if __name__ == "__main__":
    # التأكد من تشغيل السيرفر على المنفذ المناسب لـ Render
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)