-- Separate database for the automated test suite (wiped between tests). Never point tests at "tenderpilot".
CREATE DATABASE tenderpilot_test OWNER tenderpilot;
