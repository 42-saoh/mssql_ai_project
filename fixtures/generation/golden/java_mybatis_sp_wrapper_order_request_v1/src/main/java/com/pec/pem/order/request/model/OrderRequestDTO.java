package com.pec.pem.order.request.model;

import java.time.LocalDateTime;

/**
 * 주문 요청 DTO 초안.
 * evidence: dbo.USP_ORDER_REQUEST_LIST, dbo.ORD_REQ
 * 근거 보강 필요: 필드/타입은 metadata evidence 기준 초안이다.
 */
public class OrderRequestDTO {

    /** 주문요청ID */
    private Long ordReqId;

    /** 고객ID */
    private String cusId;

    /** 요청상태코드 */
    private String reqStatCd;

    /** 요청일시 */
    private LocalDateTime reqDtm;

    /** 등록사용자ID */
    private String creUsrId;

    public Long getOrdReqId() {
        return ordReqId;
    }

    public void setOrdReqId(Long ordReqId) {
        this.ordReqId = ordReqId;
    }

    public String getCusId() {
        return cusId;
    }

    public void setCusId(String cusId) {
        this.cusId = cusId;
    }

    public String getReqStatCd() {
        return reqStatCd;
    }

    public void setReqStatCd(String reqStatCd) {
        this.reqStatCd = reqStatCd;
    }

    public LocalDateTime getReqDtm() {
        return reqDtm;
    }

    public void setReqDtm(LocalDateTime reqDtm) {
        this.reqDtm = reqDtm;
    }

    public String getCreUsrId() {
        return creUsrId;
    }

    public void setCreUsrId(String creUsrId) {
        this.creUsrId = creUsrId;
    }
}
