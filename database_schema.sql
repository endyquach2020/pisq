/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19  Distrib 10.11.16-MariaDB, for Win64 (AMD64)
--
-- Host: localhost    Database: pisq
-- ------------------------------------------------------
-- Server version	10.11.16-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `classes`
--

DROP TABLE IF EXISTS `classes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `classes` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT 'Tên lớp (ví dụ: 10A1, 12D2)',
  `grade_level` tinyint(3) unsigned NOT NULL COMMENT 'Khối lớp (ví dụ: 10, 11, 12)',
  `school_year` varchar(20) DEFAULT '2024-2025' COMMENT 'Năm học',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_class_grade_year` (`name`,`grade_level`,`school_year`),
  KEY `idx_classes_grade` (`grade_level`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Quản lý thông tin lớp học và khối';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `exam_sections`
--

DROP TABLE IF EXISTS `exam_sections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `exam_sections` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `exam_id` int(10) unsigned NOT NULL COMMENT 'Đề thi sở hữu phần này',
  `section_type` enum('g1','g2','g3','g4') NOT NULL COMMENT 'Mã nhóm: g1=Nhiều lựa chọn, g2=Đúng/Sai, g3=Trả lời ngắn, g4=Tự luận',
  `title` varchar(255) NOT NULL COMMENT 'Tiêu đề hiển thị (ví dụ: PHẦN I. TRẮC NGHIỆM NHIỀU PHƯƠNG ÁN)',
  `instructions` text DEFAULT NULL COMMENT 'Lời dặn dò cho phần thi',
  `order_index` int(10) unsigned NOT NULL DEFAULT 1 COMMENT 'Thứ tự hiển thị của phần thi trong đề',
  `points` decimal(4,2) NOT NULL DEFAULT 0.00 COMMENT 'Tổng số điểm phân bổ riêng cho nhóm này',
  `shuffle_questions` tinyint(1) NOT NULL DEFAULT 1 COMMENT 'Có hoán vị câu hỏi trong nhóm không (g1, g3: TRUE; g2, g4: FALSE)',
  `shuffle_options` tinyint(1) NOT NULL DEFAULT 1 COMMENT 'Có hoán vị phương án đáp án không (g1, g2: TRUE; g3, g4: FALSE)',
  PRIMARY KEY (`id`),
  KEY `fk_sections_exam` (`exam_id`),
  CONSTRAINT `fk_sections_exam` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Phần thi phân nhóm (<#g1> đến <#g4>) và cơ chế trộn';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `exam_submissions`
--

DROP TABLE IF EXISTS `exam_submissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `exam_submissions` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `exam_id` int(10) unsigned NOT NULL,
  `student_id` int(10) unsigned NOT NULL,
  `start_time` datetime NOT NULL DEFAULT current_timestamp() COMMENT 'Thời điểm học sinh bấm bắt đầu làm',
  `submitted_at` datetime DEFAULT NULL COMMENT 'Thời điểm nộp bài',
  `score` decimal(4,2) DEFAULT NULL COMMENT 'Tổng điểm đạt được',
  `status` enum('in_progress','submitted','graded','timed_out') NOT NULL DEFAULT 'in_progress',
  `drive_upload_status` varchar(20) DEFAULT NULL,
  `drive_upload_detail` text DEFAULT NULL,
  `drive_file_id` varchar(255) DEFAULT NULL,
  `drive_file_url` text DEFAULT NULL,
  `drive_upload_attempts` int(10) unsigned NOT NULL DEFAULT 0,
  `shuffled_data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Lưu cấu trúc đề đã trộn riêng cho học sinh này (thứ tự câu/phương án)' CHECK (json_valid(`shuffled_data`)),
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `fk_sub_exam` (`exam_id`),
  KEY `idx_submissions_student` (`student_id`,`exam_id`),
  CONSTRAINT `fk_sub_exam` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_sub_student` FOREIGN KEY (`student_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Lượt nộp bài và kết quả làm bài của học sinh';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `exams`
--

DROP TABLE IF EXISTS `exams`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `exams` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL COMMENT 'Tên/Tiêu đề bài kiểm tra',
  `description` text DEFAULT NULL COMMENT 'Mô tả hoặc hướng dẫn đề thi',
  `creator_id` int(10) unsigned NOT NULL COMMENT 'Giáo viên/Admin tạo bài thi',
  `class_id` int(10) unsigned DEFAULT NULL COMMENT 'Lớp được phép làm bài thi',
  `total_score` decimal(4,2) NOT NULL DEFAULT 10.00 COMMENT 'Thang điểm tối đa (thường là 10.0)',
  `duration_minutes` int(10) unsigned NOT NULL COMMENT 'Thời gian làm bài tính bằng phút',
  `start_time` datetime DEFAULT NULL COMMENT 'Thời gian mở đề thi',
  `end_time` datetime DEFAULT NULL COMMENT 'Thời gian đóng/hết hạn nộp bài thi',
  `is_published` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Đã xuất bản cho học sinh làm hay chưa',
  `shuffle_options_globally` tinyint(1) DEFAULT 1 COMMENT 'Cho phép hoán vị phương án',
  `shuffle_questions_globally` tinyint(1) DEFAULT 1 COMMENT 'Cho phép hoán vị câu hỏi',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `fk_exams_creator` (`creator_id`),
  KEY `idx_exams_class` (`class_id`),
  KEY `idx_exams_time` (`start_time`,`end_time`),
  CONSTRAINT `fk_exams_creator` FOREIGN KEY (`creator_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_exams_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Quản lý thông tin đề thi và cấu hình phòng thi';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `question_options`
--

DROP TABLE IF EXISTS `question_options`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `question_options` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `question_id` int(10) unsigned NOT NULL COMMENT 'Câu hỏi sở hữu phương án này',
  `option_label` varchar(10) DEFAULT NULL COMMENT 'Nhãn gốc: A, B, C, D hoặc a), b), c), d)',
  `content` longtext NOT NULL COMMENT 'Nội dung đáp án (HTML, ảnh inline, LaTeX)',
  `is_correct` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Được gạch chân trong file Word (đáp án đúng)',
  `order_index` int(10) unsigned NOT NULL DEFAULT 1 COMMENT 'Thứ tự xuất hiện ban đầu',
  PRIMARY KEY (`id`),
  KEY `fk_options_question` (`question_id`),
  CONSTRAINT `fk_options_question` FOREIGN KEY (`question_id`) REFERENCES `questions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Các phương án lựa chọn hoặc mẫu trả lời ngắn';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `questions`
--

DROP TABLE IF EXISTS `questions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `questions` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `section_id` int(10) unsigned NOT NULL COMMENT 'Thuộc nhóm phần thi nào',
  `content` longtext NOT NULL COMMENT 'Nội dung câu hỏi (hỗ trợ HTML, ảnh inline, LaTeX công thức)',
  `order_index` int(10) unsigned NOT NULL DEFAULT 1 COMMENT 'Thứ tự ban đầu trong đề gốc',
  `points` decimal(4,2) NOT NULL DEFAULT 0.00 COMMENT 'Điểm câu này (nếu được chia cụ thể từ tổng điểm phần)',
  `explanation` text DEFAULT NULL COMMENT 'Lời giải chi tiết / Hướng dẫn đáp án',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `fk_questions_section` (`section_id`),
  CONSTRAINT `fk_questions_section` FOREIGN KEY (`section_id`) REFERENCES `exam_sections` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Danh sách câu hỏi của từng phần';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_answers`
--

DROP TABLE IF EXISTS `student_answers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_answers` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `submission_id` int(10) unsigned NOT NULL COMMENT 'Lượt làm bài',
  `question_id` int(10) unsigned NOT NULL COMMENT 'Câu hỏi làm',
  `selected_option_id` int(10) unsigned DEFAULT NULL COMMENT 'Phương án đã chọn (cho phần g1, g2)',
  `text_answer` longtext DEFAULT NULL COMMENT 'Câu trả lời text/ngắn (cho phần g3, g4)',
  `essay_file_url` varchar(500) DEFAULT NULL COMMENT 'Đường dẫn ảnh/file làm bài (nếu phần g4 nộp ảnh)',
  `is_correct` tinyint(1) DEFAULT NULL COMMENT 'Đúng hoặc sai (hệ thống tự chấm)',
  `awarded_points` decimal(4,2) DEFAULT 0.00 COMMENT 'Số điểm đạt được ở câu này',
  `teacher_feedback` text DEFAULT NULL COMMENT 'Nhận xét riêng của giáo viên (cho phần tự luận)',
  PRIMARY KEY (`id`),
  KEY `fk_ans_question` (`question_id`),
  KEY `idx_answers_sub_ques` (`submission_id`,`question_id`),
  CONSTRAINT `fk_ans_question` FOREIGN KEY (`question_id`) REFERENCES `questions` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ans_submission` FOREIGN KEY (`submission_id`) REFERENCES `exam_submissions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Chi tiết từng câu trả lời trong bài thi';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `class_id` int(10) unsigned DEFAULT NULL COMMENT 'Khóa ngoại tới bảng classes (chỉ áp dụng cho học sinh)',
  `username` varchar(50) NOT NULL COMMENT 'Tên đăng nhập (hoặc mã định danh/Mã học sinh)',
  `password_hash` varchar(255) NOT NULL COMMENT 'Mật khẩu đã mã hóa (bcrypt/argon2)',
  `full_name` varchar(150) NOT NULL COMMENT 'Họ và tên',
  `role` enum('admin','teacher','student') NOT NULL DEFAULT 'student' COMMENT 'Vai trò người dùng',
  `date_of_birth` date DEFAULT NULL COMMENT 'Ngày sinh',
  `gender` enum('male','female','other') DEFAULT 'other',
  `is_active` tinyint(1) NOT NULL DEFAULT 1 COMMENT 'Trạng thái hoạt động',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `fk_users_class` (`class_id`),
  KEY `idx_users_role` (`role`),
  CONSTRAINT `fk_users_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Tài khoản người dùng hệ thống';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-03  7:05:20
