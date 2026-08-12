"""PDF 导出为图片模块（基于 PyMuPDF）

用法：
    模块导入调用：
        from wulal import pdf_to_images, batch_pdf_to_images

        # 单个 PDF 导出
        images = pdf_to_images("试卷.pdf", output_dir="output/", dpi=300)

        # 目录内全部 PDF 批量导出
        images = batch_pdf_to_images("output/", dpi=200)

    命令行直接调用：
        python wulal.py 试卷.pdf [输出目录] [dpi]
        python wulal.py 批量目录/ [输出目录] [dpi]

    返回值为生成的 PNG 图片绝对路径列表，可按序插入 Word/网页。
"""
import sys
from pathlib import Path

import fitz  # PyMuPDF


# 用途：试卷经 python-docx 导出为 PDF 后，用本模块把每页渲染成 PNG，便于前端预览与嵌入网页。
def pdf_to_images(pdf_path, output_dir=None, dpi=300, prefix="page"):
    """将单个 PDF 的每一页渲染为 PNG 图片。

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录，默认与 PDF 同目录
        dpi: 渲染分辨率，默认 300（越高越清晰，文件越大）
        prefix: 图片文件名前缀，默认 "page"，生成 page_1.png、page_2.png...

    Returns:
        list[str]: 生成的图片绝对路径列表（页序）
    """
    pdf = Path(pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    out_dir = Path(output_dir) if output_dir else pdf.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    images = []
    doc = fitz.open(str(pdf))
    try:
        for i, page in enumerate(doc):
            # 获取页面渲染的图像 (pixmap)，dpi=300 保证清晰度
            pix = page.get_pixmap(dpi=dpi)
            img_path = out_dir / f"{prefix}_{i + 1}.png"
            pix.save(str(img_path))
            images.append(str(img_path))
    finally:
        doc.close()
    return images


def batch_pdf_to_images(dir_path, output_dir=None, dpi=300):
    """批量转换一个目录内的所有 PDF 文件。

    Args:
        dir_path: 存放 PDF 的目录
        output_dir: 输出目录，默认与输入目录相同
        dpi: 渲染分辨率

    Returns:
        list[str]: 所有生成的图片路径（按文件名字母序，文件内按页序）
    """
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"目录不存在: {dir_path}")

    images = []
    for pdf in sorted(dir_path.glob("*.pdf")):
        images.extend(pdf_to_images(pdf, output_dir=output_dir, dpi=dpi, prefix=pdf.stem))
    return images


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target = Path(sys.argv[1])
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    if target.is_dir():
        images = batch_pdf_to_images(target, output_dir=output_dir, dpi=dpi)
    else:
        images = pdf_to_images(target, output_dir=output_dir, dpi=dpi)

    print(f"共生成 {len(images)} 张图片：")
    for img in images:
        print(" ", img)


if __name__ == "__main__":
    main()
