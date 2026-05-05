package com.pec.pem.order.metadata.model;

import java.time.LocalDate;

/**
 * 주문 메타데이터 DTO/VO/Model VO 초안.
 * evidence: dbo.TB_ORDER
 * REVIEW_REQUIRED: 필드/타입은 metadata evidence 기준 초안이다.
 */
public class OrderMetadataVO {

    /** 주문ID */
    private Integer orderId;

    /** 고객ID */
    private Integer customerId;

    /** 주문일자 */
    private LocalDate orderDate;

    /** 상태코드 */
    private String statusCd;

    public Integer getOrderId() {
        return orderId;
    }

    public void setOrderId(Integer orderId) {
        this.orderId = orderId;
    }

    public Integer getCustomerId() {
        return customerId;
    }

    public void setCustomerId(Integer customerId) {
        this.customerId = customerId;
    }

    public LocalDate getOrderDate() {
        return orderDate;
    }

    public void setOrderDate(LocalDate orderDate) {
        this.orderDate = orderDate;
    }

    public String getStatusCd() {
        return statusCd;
    }

    public void setStatusCd(String statusCd) {
        this.statusCd = statusCd;
    }
}
