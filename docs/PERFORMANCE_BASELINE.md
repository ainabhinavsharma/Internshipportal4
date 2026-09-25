# Performance Baseline & Audit Report

## 1. Overview
Phase 19 establishing performance baseline, latency SLAs, query indexing, and caching strategy.

## 2. Route Latency Benchmarks (TTFB & Processing)

| Route | Method | Status | Min (ms) | Avg (ms) | p95 (ms) | Max (ms) | Payload (Bytes) | SLA Status |
|---|---|---|---|---|---|---|---|---|
| `/` | GET | 200 | 5.57 | 13.17 | 38.7 | 38.7 | 73792 | **PASSED** |
| `/courses` | GET | 200 | 2.73 | 6.74 | 22.03 | 22.03 | 20829 | **PASSED** |
| `/api/public/courses` | GET | 200 | 3.36 | 4.82 | 7.41 | 7.41 | 4854 | **PASSED** |
| `/jobs` | GET | 200 | 3.06 | 10.14 | 37.89 | 37.89 | 39463 | **PASSED** |
| `/internships` | GET | 200 | 8.63 | 9.92 | 12.35 | 12.35 | 119990 | **PASSED** |
| `/admin-login` | GET | 200 | 0.68 | 1.4 | 3.87 | 3.87 | 10215 | **PASSED** |

## 3. Static Asset Inventory & Size Distribution

- **Total Static Assets**: 13
- **Total Asset Footprint**: 2371.3 KB
- **Large Assets (> 500 KB)**: 2

### Top Static Assets by Size

| Asset Path | Category | Size (KB) | Optimization Status |
|---|---|---|---|
| `img/banner_student.jpg` | image | 820.1 | Needs Compression (>500KB) |
| `img/hero_student.jpg` | image | 738.2 | Needs Compression (>500KB) |
| `css/dbert-theme.css` | stylesheet | 233.5 | Optimized |
| `qr.jpg` | image | 202.3 | Optimized |
| `img/qrcode.jpeg` | image | 202.3 | Optimized |
| `js/gsap.min.js` | javascript | 70.5 | Optimized |
| `js/ScrollTrigger.min.js` | javascript | 42.4 | Optimized |
| `js/main.js` | javascript | 17.4 | Optimized |
| `js/lenis.min.js` | javascript | 12.7 | Optimized |
| `js/creative-ui.js` | javascript | 9.0 | Optimized |

## 4. Database Indexing Strategy

The following high-selectivity indexes ensure constant-time / logarithmic index scans on core queries:
- `idx_applications_status_created`: `applications(status, created_at DESC)`
- `idx_applications_email`: `applications(email)`
- `idx_enrollments_status_created`: `enrollments(payment_status, created_at DESC)`
- `idx_enrollments_email`: `enrollments(email)`
- `idx_attendance_intern_date`: `attendance(intern_id, date DESC)`
- `idx_course_day_quizzes_course`: `course_day_quizzes(course_id, day_number)`
- `idx_course_enr_email`: `course_enrollments(email)`
- `idx_posts_expires`: `posts(expires_at)`

## 5. HTTP Caching Headers

- Static Assets (`/static/...`): `Cache-Control: public, max-age=31536000, immutable`
- Authenticated User Paths (`/portal`, `/admin`, etc.): `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` (anti-back-button leak protection)

## 6. Recommendations

- Asset 'img/banner_student.jpg' is 820.1 KB. Optimize image dimensions or apply WebP compression.
- Asset 'img/hero_student.jpg' is 738.2 KB. Optimize image dimensions or apply WebP compression.
