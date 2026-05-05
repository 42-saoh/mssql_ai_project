package com.pec.pem.order.request.mapper;

import java.util.List;

import com.pec.pem.order.request.model.OrderRequestDTO;

/**
 * 주문 요청 Mapper 초안.
 * REVIEW_REQUIRED: Mapper XML namespace/sql id 와 함께 검토한다.
 */
public interface OrderRequestMapper {

    /**
     * 주문 요청 목록을 조회한다.
     *
     * @param condition 조회 조건 DTO
     * @return 주문 요청 목록
     */
    List<OrderRequestDTO> selectOrderRequestList(OrderRequestDTO condition);
}
