-- ============================================================
-- Step 0: 建库 + 选库
-- ============================================================
DROP DATABASE IF EXISTS olist;
CREATE DATABASE olist CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE olist;

-- ============================================================
-- Step 1: 建 9 张表
-- ============================================================
DROP TABLE IF EXISTS geolocation;
DROP TABLE IF EXISTS order_reviews;
DROP TABLE IF EXISTS order_payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS sellers;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS product_category_translation;

CREATE TABLE customers (
    customer_id          VARCHAR(50) PRIMARY KEY,
    customer_unique_id   VARCHAR(50) NOT NULL,
    customer_zip_code_prefix VARCHAR(10),
    customer_city        VARCHAR(100),
    customer_state       VARCHAR(5)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id                      VARCHAR(50) PRIMARY KEY,
    customer_id                   VARCHAR(50),
    order_status                  VARCHAR(20),
    order_purchase_timestamp      DATETIME,
    order_approved_at             DATETIME,
    order_delivered_carrier_date  DATETIME,
    order_delivered_customer_date DATETIME,
    order_estimated_delivery_date DATETIME
) ENGINE=InnoDB;

CREATE TABLE products (
    product_id                VARCHAR(50) PRIMARY KEY,
    product_category_name     VARCHAR(100),
    product_name_lenght       INT,
    product_description_lenght INT,
    product_photos_qty        INT,
    product_weight_g          INT,
    product_length_cm         INT,
    product_height_cm         INT,
    product_width_cm          INT
) ENGINE=InnoDB;

CREATE TABLE sellers (
    seller_id              VARCHAR(50) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(10),
    seller_city            VARCHAR(100),
    seller_state           VARCHAR(5)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_id            VARCHAR(50),
    order_item_id       INT,
    product_id          VARCHAR(50),
    seller_id           VARCHAR(50),
    shipping_limit_date DATETIME,
    price               DECIMAL(10,2),
    freight_value       DECIMAL(10,2),
    PRIMARY KEY (order_id, order_item_id)
) ENGINE=InnoDB;

CREATE TABLE order_payments (
    order_id             VARCHAR(50),
    payment_sequential   INT,
    payment_type         VARCHAR(20),
    payment_installments INT,
    payment_value        DECIMAL(10,2),
    PRIMARY KEY (order_id, payment_sequential)
) ENGINE=InnoDB;

CREATE TABLE order_reviews (
    review_id              VARCHAR(50) PRIMARY KEY,
    order_id               VARCHAR(50),
    review_score           INT,
    review_comment_title   TEXT CHARACTER SET utf8mb4,
    review_comment_message TEXT CHARACTER SET utf8mb4,
    review_creation_date   DATETIME,
    review_answer_timestamp DATETIME
) ENGINE=InnoDB;

CREATE TABLE geolocation (
    geolocation_zip_code_prefix VARCHAR(10),
    geolocation_lat             DECIMAL(10,7),
    geolocation_lng             DECIMAL(10,7),
    geolocation_city            VARCHAR(100),
    geolocation_state           VARCHAR(5)
) ENGINE=InnoDB;

CREATE TABLE product_category_translation (
    product_category_name         VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100)
) ENGINE=InnoDB;

-- ============================================================
-- Step 2: 导入 9 个 CSV (路径：MySQL Uploads 目录)
-- ============================================================
-- 选中文中每段 LOAD DATA → Ctrl+Enter 逐段执行

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/olist_customers_dataset.csv'
INTO TABLE customers
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state);

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/olist_orders_dataset.csv'
INTO TABLE orders
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(order_id, customer_id, order_status,
 @purchase, @approved, @carrier, @delivered, @estimated)
SET
 order_purchase_timestamp      = NULLIF(@purchase, ''),
 order_approved_at             = NULLIF(@approved, ''),
 order_delivered_carrier_date  = NULLIF(@carrier, ''),
 order_delivered_customer_date = NULLIF(@delivered, ''),
 order_estimated_delivery_date = NULLIF(@estimated, '');

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/olist_products_dataset.csv'
INTO TABLE products
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(product_id, product_category_name,
 @name_len, @desc_len, @photos_qty,
 @weight, @length, @height, @width)
SET
 product_name_lenght       = NULLIF(@name_len, ''),
 product_description_lenght = NULLIF(@desc_len, ''),
 product_photos_qty        = NULLIF(@photos_qty, ''),
 product_weight_g          = NULLIF(@weight, ''),
 product_length_cm         = NULLIF(@length, ''),
 product_height_cm         = NULLIF(@height, ''),
 product_width_cm          = NULLIF(@width, '');

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/olist_sellers_dataset.csv'
INTO TABLE sellers
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(seller_id, seller_zip_code_prefix, seller_city, seller_state);

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/olist_order_items_dataset.csv'
INTO TABLE order_items
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(order_id, order_item_id, product_id, seller_id,
 @shipping_limit, price, freight_value)
SET shipping_limit_date = NULLIF(@shipping_limit, '');

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/olist_order_payments_dataset.csv'
INTO TABLE order_payments
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(order_id, payment_sequential, payment_type, payment_installments, payment_value);

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/olist_order_reviews_dataset.csv'
IGNORE
INTO TABLE order_reviews
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\r\n'
IGNORE 1 ROWS
(review_id, order_id, review_score,
 review_comment_title, review_comment_message,
 @creation, @answer)
SET
 review_creation_date    = NULLIF(@creation, ''),
 review_answer_timestamp = NULLIF(@answer, '');

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/olist_geolocation_dataset.csv'
INTO TABLE geolocation
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(geolocation_zip_code_prefix, geolocation_lat, geolocation_lng,
 geolocation_city, geolocation_state);

LOAD DATA INFILE 'E:/MySQL/MySQL Server 8.0/Uploads/product_category_name_translation.csv'
INTO TABLE product_category_translation
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(@name, product_category_name_english)
SET product_category_name = TRIM(LEADING '﻿' FROM @name);

-- ============================================================
-- Step 3: 建索引
-- ============================================================
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(order_status);
CREATE INDEX idx_orders_purchase ON orders(order_purchase_timestamp);
CREATE INDEX idx_items_product ON order_items(product_id);
CREATE INDEX idx_payments_type ON order_payments(payment_type);
CREATE INDEX idx_reviews_score ON order_reviews(review_score);
CREATE INDEX idx_reviews_order ON order_reviews(order_id);
CREATE INDEX idx_customers_state ON customers(customer_state);

-- ============================================================
-- Step 4: 验证行数
-- ============================================================
SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'sellers', COUNT(*) FROM sellers
UNION ALL
SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL
SELECT 'order_payments', COUNT(*) FROM order_payments
UNION ALL
SELECT 'order_reviews', COUNT(*) FROM order_reviews
UNION ALL
SELECT 'geolocation', COUNT(*) FROM geolocation
UNION ALL
SELECT 'product_category_translation', COUNT(*) FROM product_category_translation;

-- 预期行数:
-- customers:   99,441
-- orders:      99,441
-- products:    32,951
-- sellers:      3,095
-- order_items: 112,650
-- order_payments: 103,886
-- order_reviews: 104,719
-- geolocation: 1,000,163
-- category_translation: 71