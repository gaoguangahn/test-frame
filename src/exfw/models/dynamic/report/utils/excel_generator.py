from typing import Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# 定义表格常量
HEADER_FILL = PatternFill(fill_type="solid", fgColor="4682B4")  # 表头背景色
THIN_SIDE = Side(border_style="thin", color="000000")  # 表格边框
ALL_BORDER = Border(
    left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE
)  # 表格边框
TITLE_FONT = Font(name="等线", size=10, bold=True, color="FFFFFF")  # 表头字体
DATA_FONT = Font(name="等线", size=10, color="000000")  # 表头字体
left_alignment_list = [
    "Frames",
    "Top Values",
    "values",
    "Off_Jank",
    "AnimatorFrames",
    "Values",
]


class TitleNode:
    def __init__(self, name):
        self.name = name
        self.children = []


def count_leaves(node: TitleNode):
    """
    计算叶子节点的数量
    :param node:
    :return:
    """
    if not node.children:
        return 1
    return sum(count_leaves(child) for child in node.children)


def get_all_leaf_paths(title_nodes: list[TitleNode], parent_path=""):
    """
    获取所有叶子节点的唯一路径（如 '/proc/io.read.sync'），顺序与表头一致
    """
    result = []
    for node in title_nodes:
        current_path = f"{parent_path}.{node.name}" if parent_path else node.name
        if not node.children:
            result.append(current_path)
        else:
            result.extend(get_all_leaf_paths(node.children, current_path))
    return result


def get_max_depth(nodes: list[TitleNode]):
    """
    计算树的最大深度
    :param nodes:
    :return:
    """
    if not nodes:
        return 0
    return max(1 if not n.children else 1 + get_max_depth(n.children) for n in nodes)


def merge_cells_in_ws(ws, merge_cells: list[tuple[int, int, int, int]]):
    """
    合并同一个ws中的多个单元格
    :param ws: 执行合并的ws
    :param merge_cells: 合并信息列表，每个元素为4个int：起始行，起始列，结束行，结束列
    :return:
    """
    for start_row, start_col, end_row, end_col in merge_cells:
        ws.merge_cells(
            start_row=start_row,
            start_column=start_col,
            end_row=end_row,
            end_column=end_col,
        )
        # 合并后左上角单元格设为居中
        cell = ws.cell(row=start_row, column=start_col)
        cell.font = TITLE_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.fill = HEADER_FILL
        cell.border = ALL_BORDER


def parse_titles_to_tree(titles: dict):
    """
    将标题解析为树形结构

    :param titles: dict，顶层key为sheet名，value为表头结构（list）
    :return: dict，key为sheet名，value为TitleNode列表

    示例:
        titles = {
            "task": [
                "SN", "Loops", "CaseNumber",
                {"/proc/meminfo": ["MemTotal", "MemFree", "MemAvailable", "Active(anon)"]},
                {"/proc/io": [
                    {"read": ["sync", "async"]},
                    {"write": ["sync", "async"]}
                ]}
            ]
        }
    """

    def parse_list(titles_list):
        nodes = []
        for item in titles_list:
            if isinstance(item, str):
                node = TitleNode(item)
                nodes.append(node)
            elif isinstance(item, dict):
                for k, v in item.items():
                    node = TitleNode(k)
                    # v 必须为list
                    for sub in v:
                        if isinstance(sub, str):
                            child = TitleNode(sub)
                            node.children.append(child)
                        elif isinstance(sub, dict):
                            for kk, vv in sub.items():
                                child = TitleNode(kk)
                                child.children = parse_list(vv)
                                node.children.append(child)
                    nodes.append(node)
        return nodes

    tree_dict = {}
    for sheet, title_list in titles.items():
        tree_dict[sheet] = parse_list(title_list)
    return tree_dict


def update_col_width_dict(col_width_dict: dict, col_idx: int, value: Union[str, int]):
    """
    维护col_width_dict，value为该列的最大字符串宽度（中英文按不同比例）
    :param col_width_dict: 列宽字典
    :param col_idx: 列索引
    :param value: 字符串
    :return:
    """
    if value is None:
        return
    s = str(value)
    # 中文字符按 2 宽度，英文/数字按1
    width = 0
    for c in s:
        if "\u4e00" <= c <= "\u9fff":
            width += 2
        else:
            width += 0.9
    # 适当增加间距
    width += 2
    if col_idx not in col_width_dict or width > col_width_dict[col_idx]:
        col_width_dict[col_idx] = width


def set_sheet_col_width(ws, col_width_dict: dict):
    """
    根据记录的字符宽度，设置ws的列宽
    :param ws: 数据表
    :param col_width_dict: 表格的列宽字典
    :return:
    """
    for col_idx, width in col_width_dict.items():
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width


def write_titles(
    ws, nodes: list[TitleNode], row, col, max_depth, merge_cells, col_width_dict
):
    """
    递归写入表头
    :param ws: 数据表
    :param nodes: 标题节点列表
    :param row: 写入的行
    :param col: 写入的列
    :param max_depth: 表头的最大行数
    :param merge_cells: 合并的单元格信息
    :param col_width_dict: 表格的列宽字典
    :return:
    """
    cur_col = col
    for node in nodes:
        leaf_count = count_leaves(node)
        # 横向合并
        start_col = cur_col
        end_col = cur_col + leaf_count - 1
        start_row = row
        # 判断是否叶子节点
        if not node.children:
            end_row = row + max_depth - 1
        else:
            end_row = row
        # 写入内容
        cell = ws.cell(row=start_row, column=start_col, value=node.name)
        cell.font = TITLE_FONT
        if node.name in left_alignment_list:
            cell.alignment = Alignment(horizontal="left", vertical="center")
        else:
            cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.fill = HEADER_FILL
        cell.border = ALL_BORDER
        update_col_width_dict(col_width_dict, start_col, node.name)
        # 合并单元格
        if node.children:
            # 只横向合并
            if end_col > start_col:
                merge_cells.append((start_row, start_col, end_row, end_col))
        else:
            # 只竖向合并
            if end_row > start_row:
                merge_cells.append((start_row, start_col, end_row, end_col))
        # 递归写子节点
        if node.children:
            write_titles(
                ws,
                node.children,
                row + 1,
                start_col,
                max_depth - 1,
                merge_cells,
                col_width_dict,
            )
        cur_col += leaf_count


def write_sheet_header(ws, title_nodes, col_width_dict, start_row=1):
    """
    写入表头，返回最大深度
    :param ws: 数据表
    :param title_nodes: 标题节点列表
    :param col_width_dict: 表格的列宽字典
    :param start_row: 写入的起始行
    :return: max_depth: 最大深度
    """
    if not title_nodes:
        return
    max_depth = get_max_depth(title_nodes)
    merge_cells = []
    write_titles(ws, title_nodes, start_row, 1, max_depth, merge_cells, col_width_dict)
    merge_cells_in_ws(ws, merge_cells)
    return max_depth


def write_data(ws, data_dict_list, leaf_paths, start_row, col_width_dict):
    """
    写入数据，data_dict_list按行写入
    :param ws: 当前sheet
    :param data_dict_list: 列表，每个元素是一个dict
    :param leaf_paths: 表头的顺序，即为写入的顺序
    :param start_row: 数据写入的起始行
    :param col_width_dict: 列宽字典（用于自适应列宽）
    :return:
    """
    for i, data in enumerate(data_dict_list):
        for j, path in enumerate(leaf_paths):
            value = data.get(path, "")  # 若缺失则填空
            cell = ws.cell(row=start_row + i, column=j + 1, value=value)
            cell.font = DATA_FONT
            cell.border = ALL_BORDER
            if path.split(".")[-1] in left_alignment_list:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            update_col_width_dict(col_width_dict, j + 1, value)


class ExcelGenerator:
    """excel表格生成器，只需传入表头和对应的字典数据即可生成排版表格页"""

    def __init__(self, filename):
        self.filename = filename
        self.wb = openpyxl.Workbook()
        self.sheet_map = {}

    def add_sheet(
        self, titles, data, data_writer=None, merge_cols=None, header_offset=0
    ):
        """
        添加一个sheet表格页
        :param titles: 表格页的命名和标题
        :param data: 表格内的填充数据
        :param data_writer: 数据的填充方式，默认为列表顺序写入
        :param merge_cols: 需要合并单元格的列数
        :param header_offset: 表头偏移行数
        :return:
        """
        tree_dict = parse_titles_to_tree(titles)
        # 通过for循环遍历，实际上只有一个sheet名和内容
        for sheet_name, title_nodes in tree_dict.items():
            if sheet_name in self.wb.sheetnames:
                ws = self.wb[sheet_name]
            else:
                ws = self.wb.create_sheet(sheet_name)
            self.sheet_map[sheet_name] = ws
            col_width_dict = {}
            leaf_paths = get_all_leaf_paths(title_nodes)
            header_rows = write_sheet_header(
                ws, title_nodes, col_width_dict, start_row=1 + header_offset
            )

            data_start_row = header_rows + 1 + header_offset

            if data_writer:
                data_writer(ws, data, leaf_paths, data_start_row, col_width_dict)
            else:
                write_data(ws, data, leaf_paths, data_start_row, col_width_dict)

            set_sheet_col_width(ws, col_width_dict)
            # 自动合并第一列相邻相同单元格
            # if merge_cols is None:
            #     self.merge_first_col_same_cells(ws, len(data), data_start_row)
            if merge_cols is not None:
                self.merge_specified_cols_same_cells(
                    ws, len(data), data_start_row, merge_cols
                )

    def custom_add_sheet(self, sheet_name, layout_func, *args, **kwargs):
        """
        添加一个自定义布局的sheet表格页
        :param sheet_name: 表格页的命名
        :param layout_func: 自定义布局函数，接受一个工作表对象作为参数
        """
        if sheet_name in self.wb.sheetnames:
            ws = self.wb[sheet_name]
        else:
            ws = self.wb.create_sheet(sheet_name)
        self.sheet_map[sheet_name] = ws
        layout_func(ws, *args, **kwargs)

    def merge_first_col_same_cells(self, ws, data_len, data_start_row):
        """
        合并第一列内容相同且相邻的单元格
        :param ws: 工作表
        :param data_len: 数据行数
        :param data_start_row: 数据起始行号
        """
        if data_len == 0:
            return
        current_value = ws.cell(row=data_start_row, column=1).value
        start_row = data_start_row
        for i in range(data_start_row + 1, data_start_row + data_len):
            value = ws.cell(row=i, column=1).value
            if value != current_value:
                if i - start_row > 1:
                    ws.merge_cells(
                        start_row=start_row, start_column=1, end_row=i - 1, end_column=1
                    )
                    cell = ws.cell(row=start_row, column=1)
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                current_value = value
                start_row = i
        # 最后一段
        if data_start_row + data_len - start_row > 1:
            ws.merge_cells(
                start_row=start_row,
                start_column=1,
                end_row=data_start_row + data_len - 1,
                end_column=1,
            )
            cell = ws.cell(row=start_row, column=1)
            cell.alignment = Alignment(horizontal="center", vertical="center")

    def merge_specified_cols_same_cells(self, ws, data_len, data_start_row, cols):
        """
        合并指定列内容相同且相邻的单元格，按列顺序依次合并
        :param ws: 工作表
        :param data_len: 数据行数
        :param data_start_row: 数据起始行号
        :param cols: 需要合并的列索引列表（从1开始）
        """
        if data_len == 0 or not cols:
            return

        def merge_cells_in_range(start_row, end_row, col):
            current_value = ws.cell(row=start_row, column=col).value
            merge_start_row = start_row
            for i in range(start_row + 1, end_row + 1):
                value = ws.cell(row=i, column=col).value
                if value != current_value:
                    if i - merge_start_row > 1:
                        ws.merge_cells(
                            start_row=merge_start_row,
                            start_column=col,
                            end_row=i - 1,
                            end_column=col,
                        )
                        cell = ws.cell(row=merge_start_row, column=col)
                        cell.alignment = Alignment(
                            horizontal="center", vertical="center"
                        )
                    current_value = value
                    merge_start_row = i
            if end_row + 1 - merge_start_row > 1:
                ws.merge_cells(
                    start_row=merge_start_row,
                    start_column=col,
                    end_row=end_row,
                    end_column=col,
                )
                cell = ws.cell(row=merge_start_row, column=col)
                cell.alignment = Alignment(horizontal="center", vertical="center")

        def recursive_merge(start_row, end_row, col_idx):
            if start_row < 1 or end_row < 1:
                return
            if start_row > end_row:
                return
            if col_idx >= len(cols):
                return

            col = cols[col_idx]
            if col < 1:
                return

            current_value = ws.cell(row=start_row, column=col).value
            merge_start_row = start_row
            for i in range(start_row + 1, end_row + 1):
                value = ws.cell(row=i, column=col).value
                if value != current_value:
                    if i - merge_start_row > 1:
                        merge_cells_in_range(merge_start_row, i - 1, col)
                        recursive_merge(merge_start_row, i - 1, col_idx + 1)
                    current_value = value
                    merge_start_row = i
            if end_row + 1 - merge_start_row > 1:
                merge_cells_in_range(merge_start_row, end_row, col)
                recursive_merge(merge_start_row, end_row, col_idx + 1)

        recursive_merge(data_start_row, data_start_row + data_len - 1, 0)

    def move_sheet_to_front(self, sheet_name):
        """
        将指定sheet移到Excel文件最前面
        :param sheet_name: 要移动的sheet名称
        """
        ws = self.wb[sheet_name]
        self.wb._sheets.remove(ws)
        self.wb._sheets.insert(0, ws)

    def save(self):
        if "Sheet" in self.wb.sheetnames:
            del self.wb["Sheet"]
        self.wb.save(self.filename)


if __name__ == "__main__":
    titles = {
        "task": [
            "SN",
            "Loops",
            "CaseNumber",
            {"/proc/meminfo": ["MemTotal", "MemFree", "MemAvailable", "Active(anon)"]},
            {"/proc/io": [{"read": ["sync", "async"]}, {"write": ["sync2", "async2"]}]},
        ]
    }
    data_list = [
        {
            "SN": 1,
            "Loops": 1,
            "CaseNumber": 1,
            "MemTotal": 1,
            "MemFree": 1,
            "MemAvailable": 1,
            "Active(anon)": 1,
            "sync": 1,
            "async": 1,
            "sync2": 1,
            "async2": 1,
        },
        {
            "SN": 2,
            "Loops": 2,
            "CaseNumber": 2,
            "MemTotal": 2,
            "MemFree": 2,
            "MemAvailable": 2,
            "Active(anon)": 2,
            "sync": 2,
            "async": 2,
            "sync2": 2,
            "async2": 2,
        },
        {
            "SN": 3,
            "Loops": 3,
            "CaseNumber": 3,
            "MemTotal": 3,
            "MemFree": 3,
            "MemAvailable": 3,
            "Active(anon)": 3,
            "sync": 3,
            "async": 3,
            "sync2": 3,
            "async2": 3,
        },
    ]
    path = r"D:\ptrace_analysis\analyser-script\src\report\test.xlsx"
    excel = ExcelGenerator(path)
    excel.add_sheet(titles, data_list)
    excel.save()
