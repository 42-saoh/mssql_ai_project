package com.pec.pem.order.request.service;

import java.util.List;

import com.pec.pem.order.request.model.OrderRequestDTO;

/**
 * 주문 요청 서비스 초안.
 * 근거 보강 필요: transaction boundary 는 evidence 확정 후 보강한다.
 */
public interface OrderRequestService {

    /**
     * 주문 요청 목록을 조회한다.
     *
     * @param condition 조회 조건 DTO
     * @return 주문 요청 목록
     */
    List<OrderRequestDTO> retrieveOrderRequestList(OrderRequestDTO condition);
}
