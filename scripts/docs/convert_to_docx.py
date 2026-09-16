#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将展示.md转换为展示.docx
"""

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import re
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2] if Path(__file__).parent.name == "docs" else Path(__file__).resolve().parent

def create_document():
    """创建Word文档并设置样式"""
    doc = Document()
    
    # 设置中文字体
    doc.styles['Normal'].font.name = '微软雅黑'
    doc.styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    doc.styles['Normal'].font.size = Pt(11)
    
    return doc

def add_title(doc, text, level=1):
    """添加标题"""
    p = doc.add_heading(text, level=level)
    return p

def add_paragraph_with_formatting(doc, text):
    """添加段落，处理粗体、代码等格式"""
    p = doc.add_paragraph()
    
    # 处理粗体 **text**
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            run = p.add_run(part[2:-2])
            run.bold = True
        elif part.startswith('`') and part.endswith('`'):
            run = p.add_run(part[1:-1])
            run.font.name = 'Consolas'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Consolas')
        else:
            p.add_run(part)
    
    return p

def process_markdown_to_docx(md_file, docx_file):
    """将Markdown文件转换为Word文档"""
    doc = create_document()
    
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    i = 0
    in_code_block = False
    code_block_lines = []
    
    while i < len(lines):
        line = lines[i]
        original_line = line
        line_stripped = line.strip()
        
        # 处理代码块
        if line_stripped.startswith('```'):
            if in_code_block:
                # 结束代码块
                if code_block_lines:
                    code_text = '\n'.join(code_block_lines)
                    p = doc.add_paragraph(code_text, style='No Spacing')
                    for run in p.runs:
                        run.font.name = 'Consolas'
                        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Consolas')
                        run.font.size = Pt(9)
                    code_block_lines = []
                in_code_block = False
            else:
                # 开始代码块
                in_code_block = True
            i += 1
            continue
        
        if in_code_block:
            code_block_lines.append(line)
            i += 1
            continue
        
        # 跳过空行（但保留一些空行用于格式）
        if not line_stripped:
            i += 1
            continue
        
        # 处理标题
        if line_stripped.startswith('# '):
            title = line_stripped[2:].strip()
            add_title(doc, title, level=1)
        elif line_stripped.startswith('## '):
            title = line_stripped[3:].strip()
            add_title(doc, title, level=2)
        elif line_stripped.startswith('### '):
            title = line_stripped[4:].strip()
            add_title(doc, title, level=3)
        elif line_stripped.startswith('#### '):
            title = line_stripped[5:].strip()
            add_title(doc, title, level=4)
        
        # 处理引用块
        elif line_stripped.startswith('> '):
            text = line_stripped[2:].strip()
            # 移除**标记
            text = text.replace('**', '')
            p = doc.add_paragraph(text, style='Intense Quote')
        
        # 处理分隔线
        elif line_stripped.startswith('---'):
            p = doc.add_paragraph('─' * 60)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 处理表格
        elif line_stripped.startswith('|') and '|' in line_stripped:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            i -= 1
            
            if len(table_lines) >= 2:
                # 解析表头
                headers = [cell.strip() for cell in table_lines[0].split('|')[1:-1]]
                # 跳过分隔行
                if len(table_lines) > 1 and '---' in table_lines[1]:
                    data_start = 2
                else:
                    data_start = 1
                
                # 创建表格
                table = doc.add_table(rows=1, cols=len(headers))
                table.style = 'Light Grid Accent 1'
                
                # 添加表头
                header_cells = table.rows[0].cells
                for j, header in enumerate(headers):
                    header_cells[j].text = header
                    header_cells[j].paragraphs[0].runs[0].bold = True
                
                # 添加数据行
                for row_idx in range(data_start, len(table_lines)):
                    row_line = table_lines[row_idx]
                    cells = [cell.strip() for cell in row_line.split('|')[1:-1]]
                    if len(cells) == len(headers):
                        row = table.add_row()
                        for j, cell in enumerate(cells):
                            row.cells[j].text = cell
        
        # 处理列表项
        elif line_stripped.startswith('- ') or line_stripped.startswith('* '):
            text = line_stripped[2:].strip()
            # 检查是否是动图插入位置
            if '动图插入位置' in text or '图片插入位置' in text:
                p = doc.add_paragraph()
                run = p.add_run('[动图/图片插入]')
                run.bold = True
                run.font.color.rgb = RGBColor(255, 0, 0)  # 红色标注
                p.add_run(' ' + text.replace('**', ''))
            else:
                # 移除**标记
                text = text.replace('**', '')
                doc.add_paragraph(text, style='List Bullet')
        
        # 处理编号列表
        elif re.match(r'^\s*\d+\.\s+', line_stripped):
            text = re.sub(r'^\s*\d+\.\s+', '', line_stripped)
            # 移除**标记
            text = text.replace('**', '')
            doc.add_paragraph(text, style='List Number')
        
        # 处理普通段落
        else:
            # 检查是否是动图插入位置描述
            if '动图插入位置' in line_stripped or '图片插入位置' in line_stripped:
                p = doc.add_paragraph()
                run = p.add_run('[动图/图片插入]')
                run.bold = True
                run.font.color.rgb = RGBColor(255, 0, 0)  # 红色标注
                # 移除**标记
                clean_text = line_stripped.replace('**', '')
                p.add_run(' ' + clean_text)
            else:
                # 处理包含格式的文本
                add_paragraph_with_formatting(doc, line_stripped)
        
        i += 1
    
    # 保存文档
    try:
        doc.save(docx_file)
        print(f"成功将 {md_file} 转换为 {docx_file}")
        print(f"文档已保存，共包含 {len(doc.paragraphs)} 个段落")
    except PermissionError:
        print(f"错误：无法保存文件 {docx_file}")
        print("   请先关闭该文件，然后重新运行脚本")
        return False
    
    return True

if __name__ == '__main__':
    md_file = PROJECT_ROOT / '说明文档' / '展示.md'
    docx_file = PROJECT_ROOT / '说明文档' / '展示.docx'
    
    # 检查源文件是否存在
    if not os.path.exists(md_file):
        print(f"✗ 错误：找不到源文件 {md_file}")
        exit(1)
    
    # 如果目标文件存在且被占用，使用临时文件名
    temp_file = str(docx_file) + '.tmp'
    final_file = str(docx_file)
    
    # 先尝试保存到临时文件
    success = process_markdown_to_docx(str(md_file), temp_file)
    
    if success:
        # 尝试重命名为最终文件名
        try:
            if os.path.exists(final_file):
                try:
                    os.remove(final_file)
                except PermissionError:
                    print(f"\n注意：无法覆盖现有文件 {final_file}（可能正在被使用）")
                    print(f"文档已保存为临时文件: {temp_file}")
                    print("请关闭Word中的展示.docx文件后，手动将临时文件重命名为展示.docx")
                    exit(0)
            os.rename(temp_file, final_file)
            print("\n转换完成！")
            print("提示：请在Word中打开文档，检查格式并进行必要的调整。")
        except Exception as e:
            print(f"\n重命名文件时出错: {e}")
            print(f"临时文件已保存为: {temp_file}")
            print("请手动将临时文件重命名为展示.docx")
