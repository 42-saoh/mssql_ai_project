package com.pec.pem.order.request.service;

import java.util.List;

import com.pec.pem.order.request.model.OrderRequestDTO;

/**
 * 주문 요청 서비스 초안.
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
