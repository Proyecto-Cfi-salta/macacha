CREATE DATABASE macacha_test;
\connect macacha_test
\i /docker-entrypoint-initdb.d/10-schema.sql
