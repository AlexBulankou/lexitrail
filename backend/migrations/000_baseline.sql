-- ============================================================================
-- 000_baseline.sql — the live lexitraildb schema, captured 2026-09-01 (issue-300)
--
-- WHAT THIS IS: a point-in-time capture of the schema actually running on
-- `mysql-0` in namespace `lexitrail`, produced by:
--
--   kubectl -n lexitrail exec mysql-0 -- mysqldump -uroot -p<secret> \
--     --no-data --skip-dump-date --routines --events --single-transaction lexitraildb
--
-- WHY IT EXISTS: #300 AC2. This repo has no additive-migration path, so the
-- only ways to add a column are (a) edit terraform/schema-tables.sql, which
-- DROPs all five tables, or (b) hand-run ALTER TABLE on the pod, which works
-- and leaves no artifact. (b) is the trap: it succeeds, so nothing prompts a
-- re-check, and from then on the repo's schema is a true description of a
-- database that no longer exists.
--
-- 🔑 THE TIMING IS THE POINT. Measured at capture time, the live column set is
-- IDENTICAL to terraform/schema-tables.sql -- 28 columns, both sides, with a
-- positive control confirming the comparison discriminates. Nobody has
-- hand-ALTERed yet. So this baseline is being taken at the last moment where
-- it is free; after the first (b) it becomes an archaeology problem.
--
-- ⚠️ WHAT THIS IS NOT: it is not applied by anything, and it must never be.
-- It is the KNOWN STARTING POINT that a future 001_*.sql migrates FROM. An
-- additive tool pointed at an unknown schema is a second silent-divergence
-- source rather than a fix, which is why AC2 gates AC1.
--
-- ⚠️ Live row counts at capture, so a future reader knows what a DROP costs:
--   users 2050 · recall_history 94244 · userwords 29354 · words 4472 · wordsets 9
--
-- Provenance: schema `lexitraildb` (NOT `lexitrail` — a filter on the wrong
-- name returns zero rows and reads as an empty database).
-- ============================================================================

-- MySQL dump 10.13  Distrib 8.0.46, for Linux (x86_64)
--
-- Host: localhost    Database: lexitraildb
-- ------------------------------------------------------
-- Server version	8.0.46

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
-- Temporary view structure for view `daily_recall_stats`
--

DROP TABLE IF EXISTS `daily_recall_stats`;
/*!50001 DROP VIEW IF EXISTS `daily_recall_stats`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `daily_recall_stats` AS SELECT 
 1 AS `date`,
 1 AS `unique_users`,
 1 AS `unique_words`,
 1 AS `total_recalls`,
 1 AS `user_recalls`*/;
SET character_set_client = @saved_cs_client;

--
-- Table structure for table `recall_history`
--

DROP TABLE IF EXISTS `recall_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `recall_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(320) NOT NULL,
  `word_id` int NOT NULL,
  `is_included` tinyint(1) NOT NULL,
  `recall` tinyint(1) NOT NULL,
  `recall_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `old_recall_state` int DEFAULT NULL,
  `new_recall_state` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `word_id` (`word_id`),
  CONSTRAINT `recall_history_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`email`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `recall_history_ibfk_2` FOREIGN KEY (`word_id`) REFERENCES `words` (`word_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=95209 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `email` varchar(320) NOT NULL,
  PRIMARY KEY (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `userwords`
--

DROP TABLE IF EXISTS `userwords`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `userwords` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(320) NOT NULL,
  `word_id` int NOT NULL,
  `is_included` tinyint(1) NOT NULL,
  `is_included_change_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_recall` tinyint(1) DEFAULT NULL,
  `last_recall_time` timestamp NULL DEFAULT NULL,
  `recall_state` int NOT NULL,
  `hint_img` blob,
  `hint_text` varchar(2048) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`,`word_id`),
  KEY `word_id` (`word_id`),
  CONSTRAINT `userwords_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`email`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `userwords_ibfk_2` FOREIGN KEY (`word_id`) REFERENCES `words` (`word_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=27101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `words`
--

DROP TABLE IF EXISTS `words`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `words` (
  `word_id` int NOT NULL AUTO_INCREMENT,
  `word` varchar(256) NOT NULL,
  `wordset_id` int NOT NULL,
  `def1` varchar(1024) NOT NULL,
  `def2` varchar(1024) NOT NULL,
  `hint_img` blob,
  `hint_text` varchar(2048) DEFAULT NULL,
  PRIMARY KEY (`word_id`),
  UNIQUE KEY `word` (`word`,`wordset_id`),
  KEY `wordset_id` (`wordset_id`),
  CONSTRAINT `words_ibfk_1` FOREIGN KEY (`wordset_id`) REFERENCES `wordsets` (`wordset_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6768 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `wordsets`
--

DROP TABLE IF EXISTS `wordsets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `wordsets` (
  `wordset_id` int NOT NULL AUTO_INCREMENT,
  `description` varchar(1024) NOT NULL,
  PRIMARY KEY (`wordset_id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping events for database 'lexitraildb'
--

--
-- Dumping routines for database 'lexitraildb'
--

--
-- Final view structure for view `daily_recall_stats`
--

/*!50001 DROP VIEW IF EXISTS `daily_recall_stats`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `daily_recall_stats` AS with recursive `date_series` as (select curdate() AS `date` union all select (`date_series`.`date` - interval 1 day) AS `DATE_SUB(date, INTERVAL 1 DAY)` from `date_series` where (`date_series`.`date` > (curdate() - interval 29 day))), `daily_stats` as (select cast(`recall_history`.`recall_time` as date) AS `stat_date`,`recall_history`.`user_id` AS `user_id`,count(0) AS `user_count`,count(distinct `recall_history`.`word_id`) AS `word_count` from `recall_history` where (`recall_history`.`recall_time` >= (curdate() - interval 29 day)) group by cast(`recall_history`.`recall_time` as date),`recall_history`.`user_id`) select `ds`.`date` AS `date`,count(distinct `s`.`user_id`) AS `unique_users`,sum(`s`.`word_count`) AS `unique_words`,sum(`s`.`user_count`) AS `total_recalls`,group_concat(concat(`s`.`user_id`,'(',`s`.`user_count`,')\n') order by `s`.`user_count` DESC separator '') AS `user_recalls` from (`date_series` `ds` left join `daily_stats` `s` on((`ds`.`date` = `s`.`stat_date`))) group by `ds`.`date` order by `ds`.`date` desc */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed
