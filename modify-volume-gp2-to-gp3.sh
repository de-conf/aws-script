# !/bin/bash
# 列出所有 gp2 卷 ID，并逐个转换成 gp3
for volume_id in $(aws ec2 describe-volumes --filters Name=volume-type,Values=gp2 --query 'Volumes[*].VolumeId' --output text)
do
  echo "Converting volume $volume_id to gp3..."
  aws ec2 modify-volume --volume-id $volume_id --volume-type gp3
done

