"""Shared point ledger for contribution awards and the existing shop."""
from django.conf import settings
from django.db import transaction

from .models import ObservationMedia, PointTransaction, Product, UserProfile


RANKS = (
    ('WETLAND_SPROUT', '湿地新芽', 0),
    ('PATROL_GREEN_FEATHER', '巡护青羽', 200),
    ('WATER_SILVER_FEATHER', '碧水银羽', 600),
    ('ECO_GOLD_WING', '生态金翼', 1200),
    ('ARK_GUARDIAN', '方舟守望者', 2500),
)


def rank_for(points):
    index = max(i for i, rank in enumerate(RANKS) if points >= rank[2])
    code, name, minimum = RANKS[index]
    next_rank = RANKS[index + 1] if index + 1 < len(RANKS) else None
    target = next_rank[2] if next_rank else None
    return {
        'code': code, 'name': name, 'minimumPoints': minimum,
        'maximumPoints': target - 1 if next_rank else None,
        'nextRankName': next_rank[1] if next_rank else None, 'nextRankPoints': target,
        'pointsToNextRank': target - points if next_rank else 0,
        'progressPercent': (points - minimum) * 100 // (target - minimum) if next_rank else 100,
    }


def contribution_profile(profile):
    return {
        'availablePoints': profile.score,
        'totalContributionPoints': profile.total_contribution_points,
        'completedObservationCount': profile.completed_observation_count,
        'rank': rank_for(profile.total_contribution_points),
    }


def reward_for(observation, media):
    kinds = {item.kind for item in media}
    rules = settings.CONTRIBUTION_REWARDS
    if {ObservationMedia.Kind.RGB, ObservationMedia.Kind.THERMAL} <= kinds:
        reward = rules['paired']
    else:
        reward = rules['single']
    if observation.longitude is not None and observation.latitude is not None:
        reward += rules['location']
    return reward


def _locked_profile(user_id):
    return UserProfile.objects.select_for_update().get_or_create(user_id=user_id)[0]


@transaction.atomic
def award_observation(observation, points, *, completed=False):
    profile = _locked_profile(observation.uploader_id)
    key = f'observation:{observation.pk}'
    if PointTransaction.objects.filter(idempotency_key=key).exists():
        return profile
    profile.score += points
    profile.total_contribution_points += points
    if completed:
        profile.completed_observation_count += 1
    profile.save(update_fields=['score', 'total_contribution_points', 'completed_observation_count'])
    PointTransaction.objects.create(
        user_id=profile.user_id, observation=observation, transaction_type=PointTransaction.Kind.OBSERVATION,
        points_change=points, available_points_after=profile.score, total_points_after=profile.total_contribution_points,
        idempotency_key=key, description='观测记录奖励',
    )
    return profile


class RedemptionError(Exception):
    pass


@transaction.atomic
def redeem_product(user_id, product_id, request_key):
    profile = _locked_profile(user_id)
    key = f'redeem:{user_id}:{request_key}'
    previous = PointTransaction.objects.filter(idempotency_key=key).first()
    if previous:
        if previous.product_id != product_id:
            raise RedemptionError('该兑换请求编号已用于其他商品')
        return previous.description, previous.available_points_after

    product = Product.objects.select_for_update().get(pk=product_id)
    if product.price < 0:
        raise RedemptionError('商品价格无效')
    if product.stock <= 0:
        raise RedemptionError('商品库存不足')
    if profile.score < product.price:
        raise RedemptionError(f'积分不足，还需要 {product.price - profile.score} 分')
    profile.score -= product.price
    profile.save(update_fields=['score'])
    product.stock -= 1
    product.save(update_fields=['stock'])
    PointTransaction.objects.create(
        user_id=user_id, product=product, transaction_type=PointTransaction.Kind.REDEEM,
        points_change=-product.price, available_points_after=profile.score,
        total_points_after=profile.total_contribution_points, idempotency_key=key, description=product.name,
    )
    return product.name, profile.score
