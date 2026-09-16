#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将技术特点总结.txt中的关键代码作为附录添加到展示.docx末尾
"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import re
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2] if Path(__file__).parent.name == "docs" else Path(__file__).resolve().parent

def add_code_block(doc, code_text, language='python'):
    """添加代码块到文档"""
    p = doc.add_paragraph(style='No Spacing')
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.left_indent = Inches(0.5)
    
    # 设置代码字体
    run = p.add_run(code_text)
    run.font.name = 'Consolas'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Consolas')
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0, 0, 128)  # 深蓝色代码
    
    # 设置背景色（通过段落样式）
    p.paragraph_format.keep_together = True

def add_appendix_to_docx(docx_file, tech_summary_file):
    """将技术特点总结中的关键代码添加到Word文档末尾"""
    
    # 检查文件是否存在
    if not os.path.exists(docx_file):
        print(f"错误：找不到文件 {docx_file}")
        return False
    
    # 检查文件大小
    if os.path.getsize(docx_file) == 0:
        print(f"警告：文件 {docx_file} 为空，将创建新文档")
        doc = Document()
        # 添加基本内容
        doc.add_heading('数治骑迹平台功能演示讲稿', level=1)
        doc.add_paragraph('（本文档由展示.md转换生成）')
        doc.add_page_break()
    else:
        # 打开现有文档
        try:
            doc = Document(docx_file)
        except Exception as e:
            print(f"错误：无法打开文件 {docx_file}: {e}")
            return False
    
    # 读取技术特点总结文件
    with open(tech_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 添加分页符
    doc.add_page_break()
    
    # 添加附录标题
    title = doc.add_heading('附录：关键技术代码示例', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 添加说明段落
    p_intro = doc.add_paragraph()
    p_intro.add_run('本附录展示了数治骑迹平台的核心技术实现代码，包括空间统计算法、数据处理、系统架构、指令化转译等关键模块的代码示例。这些代码体现了平台的技术创新点和工程实践水平。')
    p_intro.paragraph_format.space_after = Pt(12)
    
    # 提取所有代码块
    code_pattern = r'代码示例（([^）]+)）：\s*\n```python\s*\n(.*?)\n```'
    code_matches = re.finditer(code_pattern, content, re.DOTALL)
    
    # 组织代码块按章节分类
    code_blocks = {}
    for match in code_matches:
        file_path = match.group(1)
        code_text = match.group(2).strip()
        
        # 根据文件路径和上下文确定章节
        if 'moran_analysis' in file_path:
            if '1.1' in content[:match.start()] or '全局' in content[max(0, match.start()-200):match.start()]:
                key = ('一、空间统计算法实现', '1.1 全局与局部Moran\'s I空间自相关分析')
            else:
                key = ('三、系统架构设计', '3.3 容错与降级机制')
        elif 'hotspot_analysis' in file_path:
            key = ('一、空间统计算法实现', '1.2 Getis-Ord Gi*热点识别')
        elif 'runtime_pipeline' in file_path:
            if '字段映射' in content[max(0, match.start()-200):match.start()] or '2.1' in content[max(0, match.start()-200):match.start()]:
                key = ('二、数据处理与清洗流程', '2.1 智能字段映射与数据标准化')
            else:
                key = ('三、系统架构设计', '3.1 Runtime Pipeline轻量化架构')
        elif 'interpretation_service' in file_path:
            key = ('四、指令化转译技术', '4.1 算法结果到警务指令的智能转译')
        elif 'chart_generator' in file_path:
            key = ('五、可视化技术', '5.2 动态图表生成')
        else:
            continue
        
        if key not in code_blocks:
            code_blocks[key] = []
        code_blocks[key].append((file_path, code_text))
    
    # 按章节顺序添加代码
    section_order = [
        ('一、空间统计算法实现', [
            '1.1 全局与局部Moran\'s I空间自相关分析',
            '1.2 Getis-Ord Gi*热点识别'
        ]),
        ('二、数据处理与清洗流程', [
            '2.1 智能字段映射与数据标准化'
        ]),
        ('三、系统架构设计', [
            '3.1 Runtime Pipeline轻量化架构',
            '3.3 容错与降级机制'
        ]),
        ('四、指令化转译技术', [
            '4.1 算法结果到警务指令的智能转译'
        ]),
        ('五、可视化技术', [
            '5.2 动态图表生成'
        ])
    ]
    
    current_section = None
    for section_title, subsections in section_order:
        for subsection_title in subsections:
            key = (section_title, subsection_title)
            if key in code_blocks:
                # 添加章节标题（如果还没添加）
                if current_section != section_title:
                    doc.add_heading(section_title, level=2)
                    current_section = section_title
                
                # 添加子章节标题
                doc.add_heading(subsection_title, level=3)
                
                # 添加代码块
                for file_path, code_text in code_blocks[key]:
                    # 添加文件路径说明
                    p_file = doc.add_paragraph()
                    run = p_file.add_run(f'文件路径：{file_path}')
                    run.italic = True
                    run.font.size = Pt(10)
                    p_file.paragraph_format.space_after = Pt(6)
                    
                    # 添加代码
                    add_code_block(doc, code_text)
                    doc.add_paragraph()  # 添加空行
    
    # 添加总结段落
    doc.add_paragraph()
    p_summary = doc.add_paragraph()
    p_summary.add_run('以上代码示例展示了数治骑迹平台在空间统计算法、数据处理、系统架构、指令化转译等方面的核心技术实现。这些代码体现了平台的技术创新点，包括：')
    p_summary.paragraph_format.space_before = Pt(12)
    p_summary.paragraph_format.space_after = Pt(6)
    
    # 添加总结列表
    summary_points = [
        '轻量化Runtime Pipeline架构，实现零数据库依赖的完整分析流程',
        '智能降级机制，确保系统在任何环境下都能稳定运行',
        '指令化转译技术，将算法输出转化为可执行指令',
        '灵活字段映射，支持多种数据格式的自动适配',
        '完整的业务闭环，从数据上传到用户反馈的持续优化机制'
    ]
    
    for point in summary_points:
        p = doc.add_paragraph(point, style='List Bullet')
        p.paragraph_format.left_indent = Inches(0.5)
    
    # 保存文档
    try:
        # 尝试保存到临时文件
        temp_file = docx_file + '.tmp'
        doc.save(temp_file)
        
        # 尝试替换原文件
        try:
            if os.path.exists(docx_file):
                os.remove(docx_file)
            os.rename(temp_file, docx_file)
            print(f"[成功] 成功将附录添加到 {docx_file}")
            print(f"  文档已更新，共包含 {len(doc.paragraphs)} 个段落")
            return True
        except PermissionError:
            print(f"[警告] 无法覆盖现有文件 {docx_file}（可能正在被使用）")
            print(f"  文档已保存为临时文件: {temp_file}")
            print("  请关闭Word中的展示.docx文件后，手动将临时文件重命名为展示.docx")
            return False
    except Exception as e:
        print(f"[错误] 保存文档时出错: {e}")
        return False

if __name__ == '__main__':
    docx_file = PROJECT_ROOT / '说明文档' / '展示0.docx'
    tech_summary_file = PROJECT_ROOT / '说明文档' / '技术特点总结.txt'
    
    # 检查文件是否存在
    if not os.path.exists(docx_file):
        print(f"✗ 错误：找不到文件 {docx_file}")
        exit(1)
    
    if not os.path.exists(tech_summary_file):
        print(f"✗ 错误：找不到文件 {tech_summary_file}")
        exit(1)
    
    # 添加附录
    add_appendix_to_docx(str(docx_file), str(tech_summary_file))

