# 停车场出入场系统

基于 **Flask + YOLOv8 + EasyOCR + SQLite** 实现的模拟停车场出入场系统。

本项目通过手机网页上传车牌图片，服务器端完成车牌检测、OCR识别、车辆入场、车辆出场、停车费计算和数据存储，并提供管理员后台进行记录管理与参数配置。

## 功能简介

### 用户端功能
- 手机浏览器访问网页
- 拍照或从相册选择车牌图片
- 上传图片到服务器
- 车辆入场
- 车辆出场
- 显示识别结果、停车时长与停车费用

### 服务器端功能
- Flask HTTP 服务
- 图片上传接收与保存
- YOLOv8 车牌检测
- EasyOCR 车牌识别
- 入场 / 出场业务逻辑处理
- SQLite 数据持久化
- 异常处理

### 管理员后台功能
- 管理员密码登录
- 查看全部停车记录
- 删除指定记录
- 修改停车场总车位数
- 修改每小时收费标准
- 导出停车记录 CSV
- 查看系统统计信息

## 技术栈

- Flask
- YOLOv8
- EasyOCR
- OpenCV
- SQLite
- HTML / CSS / JavaScript

## 项目结构

```text
parking-system/
├── client/
│   ├── index.html
│   ├── admin.html
│   └── admin_login.html
├── server/
│   ├── app.py
│   ├── db.py
│   ├── ocr_service.py
│   ├── plate_detector.py
│   ├── parking.db
│   └── model/ 或 models/
│       └── best.pt
├── report.tex
└── README.md
```

## 本地运行方法

### 1. 创建虚拟环境并安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask easyocr opencv-python pillow numpy ultralytics certifi
```

### 2.启动项目

```bash
cd server
python3 app.py
```

## 云服务器部署说明
本项目已在阿里云 Ubuntu 22.04 云服务器上完成部署与测试，可通过公网 121.41.121.45 访问。

部署时需要确保：
Flask 监听地址为 0.0.0.0
云服务器安全组放行 8000 端口

启动方式：
```bash
cd /root/parking-system/server
source /root/parking-system/venv/bin/activate
python3 app.py
```
