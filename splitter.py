"""
Toplam tutarı ev arkadaşları arasında bölüştürür.
- equal: tutar kişi sayısına eşit bölünür
- by_item: her kalem 'assigned_to_user_id' varsa o kişiye, yoksa herkese eşit bölünür
"""
from models import ReceiptItem


def split_equal(total_amount: float, member_user_ids: list[str]) -> dict[str, float]:
    if not member_user_ids:
        return {}
    share = round(total_amount / len(member_user_ids), 2)
    shares = {user_id: share for user_id in member_user_ids}

    # Kuruş farklarını ilk kişiye ekleyerek toplamı tutarla eşitle
    diff = round(total_amount - share * len(member_user_ids), 2)
    if diff != 0:
        first_user = member_user_ids[0]
        shares[first_user] = round(shares[first_user] + diff, 2)

    return shares


def split_by_item(items: list[ReceiptItem], member_user_ids: list[str]) -> dict[str, float]:
    shares = {user_id: 0.0 for user_id in member_user_ids}

    for item in items:
        if item.assigned_to_user_id and item.assigned_to_user_id in shares:
            shares[item.assigned_to_user_id] += item.total_price
        else:
            # Sahibi belirtilmemiş kalemler ortak sayılır, herkese eşit dağıtılır
            per_person = item.total_price / len(member_user_ids)
            for user_id in member_user_ids:
                shares[user_id] += per_person

    return {user_id: round(amount, 2) for user_id, amount in shares.items()}
