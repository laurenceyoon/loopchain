# Copyright 2018 ICON Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""gRPC service for Peer Outer Service"""

import copy
import json
import logging

from loopchain import utils, configure as conf
from loopchain.p2p import message_code, status_code
from loopchain.p2p.bridge import PeerBridgeBase
from loopchain.p2p.protos import loopchain_pb2, loopchain_pb2_grpc


class PeerOuterService(loopchain_pb2_grpc.PeerServiceServicer):
    """secure gRPC service for outer Client or other Peer
    """

    def __init__(self, peer_bridge):
        self._peer_bridge: PeerBridgeBase = peer_bridge

        # TODO : check this handlers is using now, I thinks all useless except status
        self.__handler_map = {
            message_code.Request.status: self.__handler_status,
            message_code.Request.get_tx_result: self.__handler_get_tx_result,
            message_code.Request.get_balance: self.__handler_get_balance,
            message_code.Request.get_tx_by_address: self.__handler_get_tx_by_address,
            message_code.Request.get_total_supply: self.__handler_get_total_supply,
            message_code.Request.peer_peer_list: self.__handler_peer_list,
        }

        self.__status_cache_update_time = {}

    def __handler_status(self, request, context):
        utils.logger.debug(f"peer_outer_service:handler_status ({request.message})")

        if request.message == "get_stub_manager_to_server":
            # this case is check only gRPC available
            return loopchain_pb2.Message(code=message_code.Response.success)

        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        # FIXME : is need?
        if conf.ENABLE_REP_RADIO_STATION and request.message == "check peer status by rs":
            self._peer_bridge.channel_reset_timer(channel_name)

        status = self._peer_bridge.channel_get_peer_status_data(channel_name)
        if status is None:
            return loopchain_pb2.Message(code=message_code.Response.fail)

        meta = json.loads(request.meta) if request.meta else {}
        if meta.get("highest_block_height", None) and meta["highest_block_height"] > status["block_height"]:
            utils.logger.spam(f"(peer_outer_service.py:__handler_status) there is difference of height !")

        status_json = json.dumps(status)

        return loopchain_pb2.Message(code=message_code.Response.success, meta=status_json)

    def __handler_peer_list(self, request, context):
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        all_group_peer_list_str, peer_list_str = self._peer_bridge.channel_get_peer_list(channel_name)

        message = "All Group Peers count: " + all_group_peer_list_str

        return loopchain_pb2.Message(
            code=message_code.Response.success,
            message=message,
            meta=peer_list_str)

    def __handler_get_tx_result(self, request, context):
        """Get Transaction Result for json-rpc request
        FIXME : deprecated?

        :param request:
        :param context:
        :return:
        """
        utils.logger.spam(f"checking for test, code: {request.code}")
        utils.logger.spam(f"checking for test, channel name: {request.channel}")
        utils.logger.spam(f"checking for test, message: {request.message}")
        utils.logger.spam(f"checking for test, meta: {json.loads(request.meta)}")

        params = json.loads(request.meta)

        utils.logger.spam(f"params tx_hash({params['tx_hash']})")

        return loopchain_pb2.Message(code=message_code.Response.success)

    def __handler_get_balance(self, request, context):
        """Get Balance Tx for json-rpc request
        FIXME : deprecated?

        :param request:
        :param context:
        :return:
        """
        params = json.loads(request.meta)
        if 'address' not in params.keys():
            return loopchain_pb2.Message(code=message_code.Response.fail_illegal_params)

        query_request = loopchain_pb2.QueryRequest(params=request.meta, channel=request.channel)
        response = self.Query(query_request, context)
        utils.logger.spam(f"peer_outer_service:__handler_get_balance response({response})")

        return loopchain_pb2.Message(code=response.response_code, meta=response.response)

    def __handler_get_total_supply(self, request, context):
        """Get Total Supply
        FIXME : deprecated?

        :param request:
        :param context:
        :return:
        """
        query_request = loopchain_pb2.QueryRequest(params=request.meta, channel=request.channel)
        response = self.Query(query_request, context)
        utils.logger.spam(f"peer_outer_service:__handler_get_total_supply response({response})")

        return loopchain_pb2.Message(code=response.response_code, meta=response.response)

    def __handler_get_tx_by_address(self, request, context):
        """Get Transaction by address
        FIXME : deprecated?

        :param request:
        :param context:
        :return:
        """
        params = json.loads(request.meta)
        address = params.pop('address', None)
        index = params.pop('index', None)

        if address is None or index is None:  # or params:
            return loopchain_pb2.Message(code=message_code.Response.fail_illegal_params)

        tx_list, next_index = self._peer_bridge.channel_get_tx_by_address(request.channel, address, index)

        tx_list_dumped = json.dumps(tx_list).encode(encoding=conf.PEER_DATA_ENCODING)

        return loopchain_pb2.Message(code=message_code.Response.success,
                                     meta=str(next_index),
                                     object=tx_list_dumped)

    def Request(self, request, context):
        # utils.logger.debug(f"Peer Service got request({request.code})")

        if request.code in self.__handler_map.keys():
            return self.__handler_map[request.code](request, context)

        return loopchain_pb2.Message(code=message_code.Response.not_treat_message_code)

    def GetStatus(self, request, context):
        """Peer 의 현재 상태를 요청한다.

        :param request:
        :param context:
        :return:
        """
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL
        logging.debug("Peer GetStatus : %s", request)

        status_data = self._peer_bridge.channel_get_status_data(channel_name)

        status_data = copy.deepcopy(status_data)

        mq_status_data = self._peer_bridge.channel_mq_status_data(channel_name)

        if True in map(lambda x: 'error' in x, mq_status_data.values()):
            reason = status_code.get_status_reason(status_code.Service.mq_down)
            status_data["status"] = "Service is offline: " + reason
        status_data["mq"] = mq_status_data

        return loopchain_pb2.StatusReply(
            status=json.dumps(status_data),
            block_height=status_data["block_height"],
            total_tx=status_data["total_tx"],
            unconfirmed_block_height=status_data["unconfirmed_block_height"],
            is_leader_complaining=status_data['leader_complaint'],
            peer_id=status_data['peer_id'])

    def GetScoreStatus(self, request, context):
        """Score Service 의 현재 상태를 요청 한다

        :param request:
        :param context:
        :return:
        """
        logging.debug("Peer GetScoreStatus request : %s", request)

        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        score_status = self._peer_bridge.channel_get_score_status(channel_name)

        return loopchain_pb2.StatusReply(
            status=score_status,
            block_height=0,
            total_tx=0)

    def Stop(self, request, context):
        """Peer를 중지시킨다
        FIXME : remove this method

        :param request: 중지요청
        :param context:
        :return: 중지결과
        """

        return loopchain_pb2.StopReply(status="0")

    def Echo(self, request, context):
        """gRPC 기본 성능을 확인하기 위한 echo interface, loopchain 기능과는 무관하다.

        :return: request 를 message 되돌려 준다.
        """
        return loopchain_pb2.CommonReply(response_code=message_code.Response.success,
                                         message=request.request)

    def ComplainLeader(self, request, context):
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL
        utils.logger.notice(f"ComplainLeader {request.complain_vote}")

        self._peer_bridge.channel_complain_leader(channel_name, request.complain_vote)

        return loopchain_pb2.CommonReply(response_code=message_code.Response.success, message="success")

    def CreateTx(self, request, context):
        """make tx by client request and broadcast it to the network
        FIXME : deprecated

        :param request:
        :param context:
        :return:
        """
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL
        logging.info(f"peer_outer_service::CreateTx request({request.data}), channel({channel_name})")

        result_hash = self._peer_bridge.channel_create_tx(channel_name, request.data)

        return loopchain_pb2.CreateTxReply(
            response_code=message_code.Response.success,
            tx_hash=result_hash,
            more_info='')

    def AddTx(self, request: loopchain_pb2.TxSend, context):
        """Add tx to Block Manager

        :param request:
        :param context:
        :return:
        """

        utils.logger.spam(f"peer_outer_service:AddTx try validate_dumped_tx_message")
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        self._peer_bridge.channel_add_tx(channel_name, request)
        return loopchain_pb2.CommonReply(response_code=message_code.Response.success, message="success")

    def AddTxList(self, request: loopchain_pb2.TxSendList, context):
        """Add tx to Block Manager

        :param request:
        :param context:
        :return:
        """
        utils.logger.spam(f"peer_outer_service:AddTxList try validate_dumped_tx_message")
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        self._peer_bridge.channel_tx_receiver_add_tx_list(channel_name, request)
        return loopchain_pb2.CommonReply(response_code=message_code.Response.success, message="success")

    def GetTx(self, request, context):
        """get transaction

        :param request: tx_hash
        :param context:channel_loopchain_default
        :return:
        """
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        tx = self._peer_bridge.channel_get_tx(channel_name, request.tx_hash)

        response_code, response_msg = message_code.get_response(message_code.Response.fail)
        response_meta = ""
        response_data = ""
        response_sign = b''
        response_public_key = b''

        if tx is not None:
            response_code, response_msg = message_code.get_response(message_code.Response.success)
            response_meta = json.dumps(tx.meta)
            response_data = tx.get_data().decode(conf.PEER_DATA_ENCODING)
            response_sign = tx.signature
            response_public_key = tx.public_key

        return loopchain_pb2.GetTxReply(response_code=response_code,
                                        meta=response_meta,
                                        data=response_data,
                                        signature=response_sign,
                                        public_key=response_public_key,
                                        more_info=response_msg)

    def GetLastBlockHash(self, request, context):
        """ 마지막 블럭 조회

        :param request: 블럭요청
        :param context:
        :return: 마지막 블럭
        """
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL
        # Peer To Client
        response_code, block_hash, _, block_data_json, tx_data_json_list = \
            self._peer_bridge.channel_get_block(
                channel_name,
                block_height=-1,
                block_hash='',
                block_data_filter='block_hash',
                tx_data_filter='')

        response_code, response_msg = message_code.get_response(response_code)

        return loopchain_pb2.BlockReply(response_code=response_code,
                                        message=response_msg,
                                        block_hash=block_hash)

    def GetBlock(self, request, context):
        """Block 정보를 조회한다.

        :param request: loopchain.proto 의 GetBlockRequest 참고
         request.block_hash: 조회할 block 의 hash 값, "" 로 조회하면 마지막 block 의 hash 값을 리턴한다.
         request.block_data_filter: block 정보 중 조회하고 싶은 key 값 목록 "key1, key2, key3" 형식의 string
         request.tx_data_filter: block 에 포함된 transaction(tx) 중 조회하고 싶은 key 값 목록
        "key1, key2, key3" 형식의 string
        :param context:
        :return: loopchain.proto 의 GetBlockReply 참고,
        block_hash, block 정보 json, block 에 포함된 tx 정보의 json 리스트를 받는다.
        포함되는 정보는 param 의 filter 에 따른다.
        """

        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        response_code, block_hash, confirm_info, block_data_json, tx_data_json_list = \
            self._peer_bridge.channel_get_block(
                channel_name,
                block_height=request.block_height,
                block_hash=request.block_hash,
                block_data_filter=request.block_data_filter,
                tx_data_filter=request.tx_data_filter)

        return loopchain_pb2.GetBlockReply(response_code=response_code,
                                           block_hash=block_hash,
                                           block_data_json=block_data_json,
                                           confirm_info=confirm_info,
                                           tx_data_json=tx_data_json_list)

    def GetPrecommitBlock(self, request, context):
        """Return the precommit bock.

        :param request:
        :param context:
        :return: loopchain.proto 의 PrecommitBlockReply 참고,
        """

        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        response_code, response_message, block = \
            self._peer_bridge.channel_get_precommit_block(
                channel_name,
                last_block_height=request.last_block_height)

        return loopchain_pb2.PrecommitBlockReply(
            response_code=response_code, response_message=response_message, block=block)

    def Query(self, request, context):
        """
        FIXME : deprecated?
        """
        # channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL if request.channel == '' else request.channel

        # score_stub = StubCollection().score_stubs[channel_name]
        # response_code, response = score_stub.sync_task().query(request.params)

        return loopchain_pb2.QueryReply(response_code=message_code.Response.fail, response="{}")

    def GetInvokeResult(self, request, context):
        """get invoke result by tx_hash

        :param request: request.tx_hash = tx_hash
        :param context:
        :return: verify result
        """
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL
        logging.debug(f"peer_outer_service:GetInvokeResult in channel({channel_name})")

        response_code, result = self._peer_bridge.channel_get_invoke_result(channel_name, request.tx_hash)
        return loopchain_pb2.GetInvokeResultReply(response_code=response_code, result=result)

    def AnnounceUnconfirmedBlock(self, request, context):
        """수집된 tx 로 생성한 Block 을 각 peer 에 전송하여 검증을 요청한다.

        :param request:
        :param context:
        :return:
        """
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL
        utils.logger.debug(f"peer_outer_service::AnnounceUnconfirmedBlock channel({channel_name})")

        self._peer_bridge.channel_announce_unconfirmed_block(channel_name, request.block)
        return loopchain_pb2.CommonReply(response_code=message_code.Response.success, message="success")

    def BlockSync(self, request, context):
        # Peer To Peer
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL
        logging.info(f"BlockSync request hash({request.block_hash}) "
                     f"request height({request.block_height}) channel({channel_name})")

        response_code, block_height, max_block_height, unconfirmed_block_height, confirm_info, block_dumped = \
            self._peer_bridge.channel_block_sync(channel_name, request.block_hash, request.block_height)

        return loopchain_pb2.BlockSyncReply(
            response_code=response_code,
            block_height=block_height,
            max_block_height=max_block_height,
            confirm_info=confirm_info,
            block=block_dumped,
            unconfirmed_block_height=unconfirmed_block_height)

    def Subscribe(self, request, context):
        """BlockGenerator 가 broadcast(unconfirmed or confirmed block) 하는 채널에
        Peer 를 등록한다.

        :param request:
        :param context:
        :return:
        """
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL
        if not request.peer_id or not request.peer_target:
            return loopchain_pb2.CommonReply(
                response_code=message_code.get_response_code(message_code.Response.fail_wrong_subscribe_info),
                message=message_code.get_response_msg(message_code.Response.fail_wrong_subscribe_info)
            )

        channel_info = self._peer_bridge.peer_get_channel_infos().get(channel_name)
        peer_list = [target['peer_target'] for target in channel_info["peers"]]

        if (request.peer_target in peer_list and conf.ENABLE_CHANNEL_AUTH) or \
                (request.node_type == loopchain_pb2.CommunityNode and not conf.ENABLE_CHANNEL_AUTH):

            try:
                self._peer_bridge.channel_add_audience(channel_name, peer_target=request.peer_target)
            except KeyError:
                return loopchain_pb2.CommonReply(
                    response_code=message_code.get_response_code(message_code.Response.fail),
                    message=f"There is no channel_stubs for channel({channel_name}).")

            utils.logger.debug(f"peer_outer_service::Subscribe add_audience "
                               f"target({request.peer_target}) in channel({request.channel}), "
                               f"order({request.peer_order})")
        else:
            logging.error(f"This target({request.peer_target}, {request.node_type}) failed to subscribe.")
            return loopchain_pb2.CommonReply(response_code=message_code.get_response_code(message_code.Response.fail),
                                             message=message_code.get_response_msg("Unknown type peer"))

        return loopchain_pb2.CommonReply(response_code=message_code.get_response_code(message_code.Response.success),
                                         message=message_code.get_response_msg(message_code.Response.success))

    def UnSubscribe(self, request, context):
        """BlockGenerator 의 broadcast 채널에서 Peer 를 제외한다.

        :param request:
        :param context:
        :return:
        """
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        channel_info = self._peer_bridge.peer_get_channel_infos().get(channel_name)
        peer_list = [target['peer_target'] for target in channel_info["peers"]]

        if (request.peer_target in peer_list and conf.ENABLE_CHANNEL_AUTH) or \
                (request.node_type == loopchain_pb2.CommunityNode and not conf.ENABLE_CHANNEL_AUTH):

            try:
                self._peer_bridge.channel_remove_audience(channel_name, peer_target=request.peer_target)
            except KeyError:
                return loopchain_pb2.CommonReply(
                    response_code=message_code.get_response_code(message_code.Response.fail),
                    message=f"There is no channel_stubs for channel({channel_name}).")

            utils.logger.spam(f"peer_outer_service::Unsubscribe remove_audience target({request.peer_target}) "
                              f"in channel({request.channel})")
        else:
            logging.error(f"This target({request.peer_target}), {request.node_type} failed to unsubscribe.")
            return loopchain_pb2.CommonReply(response_code=message_code.get_response_code(message_code.Response.fail),
                                             message=message_code.get_response_msg("Unknown type peer"))

        return loopchain_pb2.CommonReply(response_code=message_code.get_response_code(message_code.Response.success),
                                         message=message_code.get_response_msg(message_code.Response.success))

    def VoteUnconfirmedBlock(self, request, context):
        channel_name = request.channel or conf.LOOPCHAIN_DEFAULT_CHANNEL

        utils.logger.debug(f"VoteUnconfirmedBlock block_hash({request.vote})")

        self._peer_bridge.channel_vote_unconfirmed_block(channel_name, vote_dumped=request.vote)

        return loopchain_pb2.CommonReply(response_code=message_code.Response.success, message="success")

    def GetChannelInfos(self, request: loopchain_pb2.GetChannelInfosRequest, context):
        """Return channels by peer target

        :param request:
        :param context:
        :return:
        """
        logging.info(f"peer_outer_service:GetChannelInfos target({request.peer_target}) "
                     f"channel_infos({self._peer_bridge.peer_get_channel_infos()})")

        return loopchain_pb2.GetChannelInfosReply(
            response_code=message_code.Response.success,
            channel_infos=json.dumps(self._peer_bridge.peer_get_channel_infos())
        )