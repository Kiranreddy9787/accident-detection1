-- MySQL dump 10.13  Distrib 8.0.44, for Win64 (x86_64)
--
-- Host: localhost    Database: accident_detection
-- ------------------------------------------------------
-- Server version	8.0.44

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `accident_detection`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `accident_detection` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `accident_detection`;

--
-- Table structure for table `accident_event`
--

DROP TABLE IF EXISTS `accident_event`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `accident_event` (
  `accident_event_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `detection_log_id` bigint unsigned NOT NULL,
  `severity_level_id` tinyint unsigned NOT NULL,
  `event_status` enum('detected','verified','resolved','false_positive') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'detected',
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `verified_by_user_id` int unsigned DEFAULT NULL,
  `verified_at` timestamp NULL DEFAULT NULL,
  `resolved_at` timestamp NULL DEFAULT NULL,
  `snapshot_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`accident_event_id`),
  UNIQUE KEY `detection_log_id` (`detection_log_id`),
  KEY `fk_accident_event_verified_by` (`verified_by_user_id`),
  KEY `idx_accident_event_status_time` (`event_status`,`occurred_at`),
  KEY `idx_accident_event_severity` (`severity_level_id`),
  CONSTRAINT `fk_accident_event_detection` FOREIGN KEY (`detection_log_id`) REFERENCES `detection_log` (`detection_log_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_accident_event_severity` FOREIGN KEY (`severity_level_id`) REFERENCES `severity_level` (`severity_level_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_accident_event_verified_by` FOREIGN KEY (`verified_by_user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `accident_event`
--

LOCK TABLES `accident_event` WRITE;
/*!40000 ALTER TABLE `accident_event` DISABLE KEYS */;
/*!40000 ALTER TABLE `accident_event` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `alerts`
--

DROP TABLE IF EXISTS `alerts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alerts` (
  `alert_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `accident_event_id` bigint unsigned NOT NULL,
  `emergency_contact_id` int unsigned DEFAULT NULL,
  `alert_channel` enum('sms','email','call','dashboard') COLLATE utf8mb4_unicode_ci NOT NULL,
  `alert_status` enum('pending','sent','delivered','failed','acknowledged') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `alert_message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `sent_at` timestamp NULL DEFAULT NULL,
  `acknowledged_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`alert_id`),
  KEY `fk_alerts_emergency_contact` (`emergency_contact_id`),
  KEY `idx_alerts_event_status` (`accident_event_id`,`alert_status`),
  CONSTRAINT `fk_alerts_accident_event` FOREIGN KEY (`accident_event_id`) REFERENCES `accident_event` (`accident_event_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_alerts_emergency_contact` FOREIGN KEY (`emergency_contact_id`) REFERENCES `emergency_contacts` (`emergency_contact_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alerts`
--

LOCK TABLES `alerts` WRITE;
/*!40000 ALTER TABLE `alerts` DISABLE KEYS */;
/*!40000 ALTER TABLE `alerts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cameras`
--

DROP TABLE IF EXISTS `cameras`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cameras` (
  `camera_id` int unsigned NOT NULL AUTO_INCREMENT,
  `camera_name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `location_description` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `stream_url` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('active','inactive','maintenance') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'inactive',
  `created_by_user_id` int unsigned DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`camera_id`),
  KEY `fk_cameras_created_by` (`created_by_user_id`),
  CONSTRAINT `fk_cameras_created_by` FOREIGN KEY (`created_by_user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cameras`
--

LOCK TABLES `cameras` WRITE;
/*!40000 ALTER TABLE `cameras` DISABLE KEYS */;
/*!40000 ALTER TABLE `cameras` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `detection_log`
--

DROP TABLE IF EXISTS `detection_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `detection_log` (
  `detection_log_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `camera_id` int unsigned NOT NULL,
  `detected_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `model_name` varchar(120) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `model_version` varchar(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `confidence_score` decimal(5,4) DEFAULT NULL,
  `source_frame_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`detection_log_id`),
  KEY `idx_detection_log_camera_detected` (`camera_id`,`detected_at`),
  CONSTRAINT `fk_detection_log_camera` FOREIGN KEY (`camera_id`) REFERENCES `cameras` (`camera_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_detection_confidence` CHECK (((`confidence_score` is null) or (`confidence_score` between 0 and 1)))
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `detection_log`
--

LOCK TABLES `detection_log` WRITE;
/*!40000 ALTER TABLE `detection_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `detection_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `emergency_contacts`
--

DROP TABLE IF EXISTS `emergency_contacts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `emergency_contacts` (
  `emergency_contact_id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int unsigned DEFAULT NULL,
  `contact_name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `organization` varchar(120) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `phone_number` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `contact_type` enum('police','ambulance','fire','hospital','administrator','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`emergency_contact_id`),
  KEY `fk_emergency_contacts_user` (`user_id`),
  CONSTRAINT `fk_emergency_contacts_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `emergency_contacts`
--

LOCK TABLES `emergency_contacts` WRITE;
/*!40000 ALTER TABLE `emergency_contacts` DISABLE KEYS */;
/*!40000 ALTER TABLE `emergency_contacts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notification_log`
--

DROP TABLE IF EXISTS `notification_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notification_log` (
  `notification_log_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `alert_id` bigint unsigned NOT NULL,
  `emergency_contact_id` int unsigned DEFAULT NULL,
  `delivery_status` enum('queued','sent','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'queued',
  `provider_message_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `provider_response` text COLLATE utf8mb4_unicode_ci,
  `attempted_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `delivered_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`notification_log_id`),
  KEY `fk_notification_log_contact` (`emergency_contact_id`),
  KEY `idx_notification_log_alert` (`alert_id`,`attempted_at`),
  CONSTRAINT `fk_notification_log_alert` FOREIGN KEY (`alert_id`) REFERENCES `alerts` (`alert_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_notification_log_contact` FOREIGN KEY (`emergency_contact_id`) REFERENCES `emergency_contacts` (`emergency_contact_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notification_log`
--

LOCK TABLES `notification_log` WRITE;
/*!40000 ALTER TABLE `notification_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `notification_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `severity_level`
--

DROP TABLE IF EXISTS `severity_level`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `severity_level` (
  `severity_level_id` tinyint unsigned NOT NULL AUTO_INCREMENT,
  `level_name` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `priority_order` tinyint unsigned NOT NULL,
  `description` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`severity_level_id`),
  UNIQUE KEY `level_name` (`level_name`),
  UNIQUE KEY `priority_order` (`priority_order`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `severity_level`
--

LOCK TABLES `severity_level` WRITE;
/*!40000 ALTER TABLE `severity_level` DISABLE KEYS */;
INSERT INTO `severity_level` VALUES (1,'Low',1,'Minor incident requiring observation.','2026-09-10 18:34:50'),(2,'Medium',2,'Incident requiring prompt review.','2026-09-10 18:34:50'),(3,'High',3,'Serious incident requiring immediate action.','2026-09-10 18:34:50');
/*!40000 ALTER TABLE `severity_level` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `user_id` int unsigned NOT NULL AUTO_INCREMENT,
  `full_name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('admin','operator') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'operator',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
-- Seed no user accounts; create the first admin through the app setup screen.

/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'accident_detection'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-11 18:04:29
