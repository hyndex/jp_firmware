import asyncio
import logging
from datetime import datetime

from ocpp.v16 import call
from ocpp.v16.enums import AuthorizationStatus, Reason

async def authorize(charge_point, id_tag):
    """
    Checks the authorization status of an ID tag.
    """
    request = call.AuthorizePayload(id_tag=id_tag)
    response = await charge_point.call(request)
    return response.id_tag_info['status'] == AuthorizationStatus.accepted

async def start_transaction(charge_point, connector_id, id_tag):
    """
    Initiates a charging transaction for a specified connector and ID tag after authorization.
    """
    authorized = await authorize(charge_point, id_tag)
    if not authorized:
        logging.warning(f"Authorization denied for ID tag {id_tag}.")
        return {'status': 'Rejected'}

    if connector_id in charge_point.active_transactions:
        logging.error(f"Transaction already active on connector {connector_id}")
        return {'status': 'Rejected'}

    meter_start = charge_point.get_meter_value(connector_id)
    request = call.StartTransactionPayload(
        connector_id=connector_id,
        id_tag=id_tag,
        meter_start=meter_start,
        timestamp=datetime.utcnow().isoformat()
    )
    response = await charge_point.call(request)
    if response.id_tag_info['status'] == 'Accepted':
        charge_point.active_transactions[connector_id] = {
            "transaction_id": response.transaction_id,
            "id_tag": id_tag,
            "meter_start": meter_start,
            "start_time": datetime.now()
        }
        logging.info(f"Transaction {response.transaction_id} started on connector {connector_id}")
        return {'status': 'Accepted'}
    else:
        logging.warning(f"Transaction start denied for ID tag {id_tag} on connector {connector_id}")
        return {'status': 'Rejected'}

async def stop_transaction(charge_point, connector_id, reason='Remote'):
    """
    Stops an active charging transaction for a specified connector.
    """
    transaction = charge_point.active_transactions.get(connector_id, None)
    if not transaction:
        logging.error(f"No active transaction found on connector {connector_id}")
        return {'status': 'Rejected'}

    meter_stop = charge_point.get_meter_value(connector_id)
    request = call.StopTransactionPayload(
        meter_stop=meter_stop,
        timestamp=datetime.utcnow().isoformat(),
        transaction_id=transaction['transaction_id'],
        reason=Reason[reason]
    )
    response = await charge_point.call(request)
    del charge_point.active_transactions[connector_id]
    logging.info(f"Transaction {transaction['transaction_id']} stopped on connector {connector_id}")
    return {'status': 'Accepted'}

async def remote_start_transaction(charge_point, connector_id, id_tag):
    """
    Handles the request to start a transaction remotely by adding it to the queue.
    """
    logging.info(f"Queueing remote start for connector {connector_id} with ID tag {id_tag}")
    await charge_point.function_call_queue.put((start_transaction, [charge_point, connector_id, id_tag], {}))

async def remote_stop_transaction(charge_point, transaction_id):
    """
    Handles the request to stop a transaction remotely by searching for the transaction and adding the stop request to the queue.
    """
    for connector_id, transaction in charge_point.active_transactions.items():
        if transaction['transaction_id'] == transaction_id:
            logging.info(f"Queueing remote stop for transaction {transaction_id}")
            await charge_point.function_call_queue.put((stop_transaction, [charge_point, connector_id, 'Remote'], {}))
            return {'status': 'Accepted'}
    return {'status': 'Rejected'}
