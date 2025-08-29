import boto3
from datetime import datetime, timezone, timedelta
from colorama import Fore, Style, init
from collections import defaultdict

# 初始化 colorama
init(autoreset=True)

# 标准化因子表
NORMALIZATION_FACTORS = {
    "nano": 0.25,
    "micro": 0.5,
    "small": 1,
    "medium": 2,
    "large": 4,
    "xlarge": 8,
    "2xlarge": 16,
    "3xlarge": 24,
    "4xlarge": 32,
    "6xlarge": 48,
    "8xlarge": 64,
    "9xlarge": 72,
    "10xlarge": 80,
    "12xlarge": 96,
    "16xlarge": 128,
    "18xlarge": 144,
    "24xlarge": 192,
    "32xlarge": 256,
    "56xlarge": 448,
    "112xlarge": 896,
}

def get_normalization_factor(instance_type: str) -> float:
    """提取 instance_type 中的大小部分并返回标准化因子"""
    try:
        size = instance_type.split(".")[1]
        return NORMALIZATION_FACTORS.get(size, 0)
    except Exception:
        return 0

def get_instance_family(instance_type: str) -> str:
    """从实例类型中提取实例族"""
    try:
        return instance_type.split(".")[0]
    except IndexError:
        return "Unknown"

def get_running_instances(ec2):
    """获取正在运行的实例"""
    reservations = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )["Reservations"]

    instances = []
    for res in reservations:
        for inst in res["Instances"]:
            itype = inst["InstanceType"]
            nf = get_normalization_factor(itype)
            family = get_instance_family(itype)
            instances.append({
                "InstanceId": inst["InstanceId"],
                "InstanceType": itype,
                "NormalizationFactor": nf,
                "Family": family,  # 添加 Family 字段
            })
    return instances

def get_reserved_instances(ec2):
    """获取有效的预留实例"""
    reserved = ec2.describe_reserved_instances(
        Filters=[{"Name": "state", "Values": ["active"]}]
    )["ReservedInstances"]

    reservations = []
    for r in reserved:
        itype = r["InstanceType"]
        nf = get_normalization_factor(itype)
        qty = r["InstanceCount"]
        convertible = r["OfferingClass"] == "convertible"
        end = r["End"]
        family = get_instance_family(itype) # 添加 Family 字段
        reservations.append({
            "InstanceType": itype,
            "NormalizationFactor": nf,
            "Count": qty,
            "TotalNF": nf * qty,
            "Convertible": convertible,
            "End": end,
            "Family": family,  # 添加 Family 字段
        })
    return reservations

def print_running_instances(instances):
    print("\n===== 当前运行实例 =====")
    total_nf = 0
    running_by_family = defaultdict(float) # 用于按族聚合
    for inst in instances:
        print(
            f"实例 {inst['InstanceId']} | 类型: {inst['InstanceType']} "
            f"| 标准化因子: {inst['NormalizationFactor']} | 族: {inst['Family']}"
        )
        total_nf += inst["NormalizationFactor"]
        running_by_family[inst['Family']] += inst["NormalizationFactor"]
    print(f"总标准化积分: {total_nf}\n")
    return running_by_family # 返回按族聚合的字典

def print_reserved_instances(reservations):
    print("\n===== 预留实例 =====")
    total_nf = 0
    reserved_by_family = defaultdict(lambda: {"fixed": 0.0, "convertible": 0.0}) # 用于按族和可转换性聚合
    now = datetime.now(timezone.utc)
    for r in reservations:
        time_left = r["End"] - now
        end_str = r["End"].strftime("%Y-%m-%d %H:%M:%S")
        if time_left <= timedelta(days=5):
            end_str = Fore.RED + end_str + " (即将到期)" + Style.RESET_ALL

        print(
            f"实例类型: {r['InstanceType']} | 数量: {r['Count']} "
            f"| 单个因子: {r['NormalizationFactor']} | 总因子: {r['TotalNF']} "
            f"| 可转换: {r['Convertible']} | 到期: {end_str} | 族: {r['Family']}"
        )
        total_nf += r["TotalNF"]
        if r['Convertible']:
            reserved_by_family[r['Family']]["convertible"] += r["TotalNF"]
        else:
            reserved_by_family[r['Family']]["fixed"] += r["TotalNF"]
    print(f"预留实例总标准化积分: {total_nf}\n")
    return reserved_by_family # 返回按族和可转换性聚合的字典

def compare_instances(running_by_family, reserved_by_family):
    print("\n===== 差值计算 (按实例族) =====")

    all_families = set(running_by_family.keys()).union(set(reserved_by_family.keys()))

    for family in sorted(list(all_families)):
        running_nf = running_by_family.get(family, 0)

        # 预留实例分为固定型和可转换型
        fixed_reserved_nf = reserved_by_family.get(family, {}).get("fixed", 0)
        convertible_reserved_nf = reserved_by_family.get(family, {}).get("convertible", 0)

        # 对于差值计算，我们首先尝试使用固定型预留实例
        # 可转换型预留实例可以用于任何实例族，因此在族内计算时，我们先考虑固定匹配
        # 实际的成本优化逻辑会更复杂，这里仅在族内展示优先级

        diff = running_nf - fixed_reserved_nf

        output_message = (
            f"{family} 系列 | 运行中实例积分: {running_nf} - "
            f"固定预留实例积分: {fixed_reserved_nf}"
        )

        if convertible_reserved_nf > 0:
             output_message += f" (可转换预留积分: {convertible_reserved_nf})"

        if diff > 0:
            # 运行中超过固定预留，查看是否有可转换预留可以弥补
            remaining_diff = diff - convertible_reserved_nf
            if remaining_diff > 0:
                print(
                    Fore.YELLOW + output_message + f" = 差值: {diff} ⚠️ 运行中实例超过预留实例 {remaining_diff} 积分 (即使考虑可转换型)" + Style.RESET_ALL
                )
            else:
                print(
                    Fore.CYAN + output_message + f" = 差值: {diff} ✅ 运行中实例由可转换预留覆盖" + Style.RESET_ALL
                )
        elif diff < 0:
            # 固定预留超过运行中
            print(
                Fore.GREEN + output_message + f" = 差值: {diff} ✅ 预留实例超过运行实例 {abs(diff)} 积分" + Style.RESET_ALL
            )
        else:
            # 完全匹配，或者运行中和固定预留匹配，可转换的暂时没用到
            if convertible_reserved_nf > 0:
                print(
                    Fore.CYAN + output_message + f" = 差值: {diff} ✅ 固定预留完全匹配运行中实例 (有 {convertible_reserved_nf} 可转换预留未使用)" + Style.RESET_ALL
                )
            else:
                print(Fore.CYAN + output_message + f" = 差值: {diff} 完全匹配，无差异" + Style.RESET_ALL)
    print("\n注意: 可转换预留实例可以灵活应用于不同实例族，上述计算为族内固定匹配的初步估算。")


def main():
    session = boto3.Session()
    ec2 = session.client("ec2")

    running_instances = get_running_instances(ec2)
    reserved_instances = get_reserved_instances(ec2)

    # 修改此处，接收按族聚合的结果
    running_by_family_nf = print_running_instances(running_instances)
    reserved_by_family_nf = print_reserved_instances(reserved_instances)

    compare_instances(running_by_family_nf, reserved_by_family_nf)

if __name__ == "__main__":
    main()
