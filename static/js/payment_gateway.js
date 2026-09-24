/**
 * static/js/payment_gateway.js - Razorpay Payment Gateway & Dynamic Fallback Helper
 * Implements Phase 8 requirements of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md
 * 
 * Automatically detects whether Razorpay credentials are configured.
 * - When enabled: injects fast, secure Razorpay checkout modal.
 * - When disabled or if user closes modal: preserves manual UPI QR code and screenshot flow.
 */

(function () {
    "use strict";

    let _paymentConfig = null;
    let _scriptLoadingPromise = null;

    async function fetchConfig() {
        if (_paymentConfig) return _paymentConfig;
        try {
            const res = await fetch("/api/payment/config");
            _paymentConfig = await res.json();
            return _paymentConfig;
        } catch (e) {
            console.warn("Could not fetch payment gateway config:", e);
            _paymentConfig = { enabled: false, key_id: "", fallback_available: true };
            return _paymentConfig;
        }
    }

    function loadRazorpayScript() {
        if (window.Razorpay) return Promise.resolve(true);
        if (_scriptLoadingPromise) return _scriptLoadingPromise;

        _scriptLoadingPromise = new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://checkout.razorpay.com/v1/checkout.js";
            script.async = true;
            script.onload = () => resolve(true);
            script.onerror = () => {
                console.error("Failed to load Razorpay checkout script.");
                resolve(false);
            };
            document.head.appendChild(script);
        });

        return _scriptLoadingPromise;
    }

    async function initiateRazorpayPayment(opts) {
        const {
            productType = "security_deposit",
            productId = null,
            domain = "",
            joiningDate = "",
            onSuccess = null,
            onError = null
        } = opts || {};

        const cfg = await fetchConfig();
        if (!cfg.enabled) {
            if (onError) onError(new Error("Razorpay is not enabled. Please use the manual UPI QR code."));
            return false;
        }

        const scriptLoaded = await loadRazorpayScript();
        if (!scriptLoaded || !window.Razorpay) {
            alert("Could not load online payment gateway. Please use the UPI QR code below.");
            if (onError) onError(new Error("Script loading failed"));
            return false;
        }

        // 1. Create order on server (canonical pricing)
        let orderData;
        try {
            const res = await fetch("/api/payment/razorpay/create-order", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({
                    product_type: productType,
                    product_id: productId,
                    domain: domain,
                    joining_date: joiningDate
                })
            });

            orderData = await res.json();
            if (orderData.status !== "success") {
                throw new Error(orderData.message || "Failed to create payment order");
            }
        } catch (err) {
            console.error("Order creation error:", err);
            alert(err.message || "Could not initialize payment. Please use manual UPI.");
            if (onError) onError(err);
            return false;
        }

        // 2. Open Razorpay Checkout modal
        const rzpOptions = {
            key: orderData.key_id,
            amount: orderData.amount,
            currency: orderData.currency || "INR",
            name: "DBERT Internship Portal",
            description: productType === "paid_program" ? "Fast-Track Program Fee" : "Internship Security Deposit",
            image: "/static/img/hero_student.jpg",
            order_id: orderData.order_id,
            handler: async function (response) {
                // 3. Verify signature on backend
                try {
                    const verifyRes = await fetch("/api/payment/razorpay/verify-payment", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        credentials: "include",
                        body: JSON.stringify({
                            razorpay_order_id: response.razorpay_order_id,
                            razorpay_payment_id: response.razorpay_payment_id,
                            razorpay_signature: response.razorpay_signature,
                            product_type: productType,
                            product_id: productId,
                            domain: domain,
                            joining_date: joiningDate
                        })
                    });

                    const verifyData = await verifyRes.json();
                    if (verifyData.status === "success") {
                        if (onSuccess) {
                            onSuccess(verifyData);
                        } else {
                            window.location.href = verifyData.redirect || "/portal";
                        }
                    } else {
                        alert(verifyData.message || "Payment verification failed. Please contact admissions.");
                        if (onError) onError(new Error(verifyData.message));
                    }
                } catch (verifyErr) {
                    console.error("Verification error:", verifyErr);
                    alert("Network error during payment verification. If amount was deducted, it will reconcile automatically.");
                    if (onError) onError(verifyErr);
                }
            },
            modal: {
                ondismiss: function () {
                    console.log("Razorpay checkout modal closed by user. Fallback QR remains available.");
                }
            },
            theme: {
                color: "#4F46E5"
            }
        };

        const rzp = new window.Razorpay(rzpOptions);
        rzp.open();
        return true;
    }

    // Expose public API
    window.DBERTPayment = {
        fetchConfig,
        initiateRazorpayPayment,
        loadRazorpayScript
    };

    // Auto-setup button enhancements if container present
    document.addEventListener("DOMContentLoaded", async () => {
        const cfg = await fetchConfig();
        if (!cfg.enabled) {
            // Keep manual UPI as the sole UI
            return;
        }

        // If Razorpay is enabled, we can bind any button with data-razorpay-trigger
        document.querySelectorAll("[data-razorpay-trigger]").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.preventDefault();
                const productType = btn.dataset.productType || "security_deposit";
                const productId = btn.dataset.productId || null;
                const domain = btn.dataset.domain || "";
                const joiningDate = btn.dataset.joiningDate || "";
                initiateRazorpayPayment({ productType, productId, domain, joiningDate });
            });
        });
    });
})();
