# aircraft-reg-scanner

A local offline pipeline to identify aircraft type from images via OCR and OpenSky database.

## Brief Intro

Using database from Opensky: [OpenSky](https://opensky-network.org/data/aircraft) and [Opensky Data Samples](https://opensky-network.org/datasets/#metadata/).

This project is mainly for Chinese user as all output contains Chinese.

Developed with Gemini AI

Now working on:

1. More accurate OCR(text filter)
2. Implement YOLO for OCR
3. Manual correction module for database

## How to use

Warning:  There mighy be bugs so use at your own risks.

1. Download as zip
2. Put photos in `images` folder
3. Run `main.py`

Since it has not been packaged yet, it is recommended to use VS Code or other editor instead of double-clicking the file directly.

## 简要介绍

注意：开发初期代码功能不完整，可能有bug，使用者后果自负

一个通过 OCR 和 OpenSky 数据库从图像中识别注册号和机型的本地离线系统

使用OpenSky数据库：[OpenSky](https://opensky-network.org/data/aircraft) 和 [Opensky Data Samples](https://opensky-network.org/datasets/#metadata/)

与Gemini AI一同开发

现正开发：

1. 更准确的OCR识别过滤系统
2. 使用YOLO对精确区域进行识别以提升准确率
3. 人工介入数据库纠正

## 如何使用

1. 打包下载代码
2. 把需要识别的图片放到 `images` 文件夹中
3. 运行 `main.py`

由于目前尚未封装,推荐使用VS Code或其他编辑器,而非直接双击文件

## Update Log

UPD @ 2026/6/15:Ver 0.0 基本架构

UPD @ 2026/6/15:Ver 0.1 现已可以识别简单工况; 现已可以对航司数据进行OCR识别并在与数据库不同时弹出警告

UPD @ 2026/6/15:Ver 0.1b 现已可以对目标文件夹批量识别

UPD @ 2026/6/15:Ver 0.2 导入ICAO国家前缀并提升混淆辨别能力(查询数据库中混淆编号是否存在)

UPD @ 2026/6/15:Ver 0.2b 现已可以自动选择CPU或GPU运算,提升运算速度;修正了数据库中地区名称;输出时同时输出匹配国家(地区)以便核验

UPD @ 2026/6/15:Ver 0.2c db文件已上传;readme更新了"如何使用"部分
