<?php
// Tự động chuyển hướng từ Apache (cổng 80) sang PisQ FastAPI (cổng 8000)
$host = isset($_SERVER['HTTP_HOST']) ? explode(':', $_SERVER['HTTP_HOST'])[0] : 'localhost';
$backend_url = "http://" . $host . ":8000/";

header("Location: " . $backend_url);
exit;
