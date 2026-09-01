# -*- coding: utf-8 -*-
"""PSV Engine 唯一启动入口。
v35 单一数据源铁律：启动即打印唯一数据根事实——一个运行实例 = 一个数据根 = 一个数据库。
"""
from core.config import settings
from core.webui.app import run

if __name__ == '__main__':
    info = settings.data_root_info()
    print('=' * 64)
    print('PSV Engine %s' % settings.VERSION)
    print('DATA ROOT : %s' % info['data_root'])
    print('DATABASE  : %s (%s, %d bytes)' % (info['database'], 'exists' if info['exists'] else 'new', info['size_bytes']))
    print('全部节点 / API / UI 共享此唯一数据库；若与预期不符，检查 DATABASE_PATH 环境变量。')
    print('=' * 64)
    run()
