#!/bin/bash
set -e

# print all pod stats and export kind logs when job failed
cleanup() {
  echo "pods in all namespaces"
  kubectl get pod --all-namespaces
  echo "events in all namespaces"
  kubectl get events --all-namespaces
  echo "export kind logs"
  mkdir -p kind_logs
  kind export logs --name primehub kind_logs
}
trap "cleanup" ERR

wait_for_docker() {
  local now=$SECONDS
  local timeout=600
  while true; do
    # it might fail
    echo "checking docker"
    set +e
    docker info > /dev/null 2>&1
    ret=$?
    set -e
    if [ "$ret" == "0" ]; then
      echo "docker is available now"
      break
    fi
    if (( $SECONDS - now > $timeout )); then
      return 1
    fi
    sleep 5
  done
  return 0
}

wait_for_pod() {
  local name=$1
  local now=$SECONDS
  local timeout=600
  while true; do
    # it might fail
    echo "Checking ${name} up..."
    set +e
    kubectl get pods -n hub -l app.kubernetes.io/name=${name} | grep "2/2" > /dev/null 2>&1
    ret=$?
    set -e
    if [ "$ret" == "0" ]; then
      echo "${name} is available now"
      break
    fi
    if (( $SECONDS - now > $timeout )); then
      return 1
    fi
    sleep 5
  done
  return 0
}

# sync submodules
git submodule init && git submodule sync && git submodule update --init --recursive && git submodule status

# enable docker in docker
echo "start docker in docker"
sudo ci/start.sh &

export CLUSTER_NAME="primehub"
export BIND_ADDRESS=10.88.88.88
export PRIMEHUB_SCHEME="http"
export PRIMEHUB_DOMAIN="hub.ci-e2e.dev.primehub.io"
export PRIMEHUB_PORT=$(( $RANDOM % 50000 + 10000 ))
export KC_SCHEME="http"
export KC_DOMAIN="id.ci-e2e.dev.primehub.io"
export KC_PORT=${PRIMEHUB_PORT}
export PH_USERNAME="phadmin"
export PH_PASSWORD=$(openssl rand -hex 16)
export PRIMEHUB_STORAGE_CLASS=local-path
export PRIMEHUB_MODE=${PRIMEHUB_MODE:-ce}

rm -f env_file
echo CLUSTER_NAME=$CLUSTER_NAME >> env_file
echo BIND_ADDRESS=$BIND_ADDRESS >> env_file
echo PRIMEHUB_SCHEME=$PRIMEHUB_SCHEME >> env_file
echo PRIMEHUB_DOMAIN=$PRIMEHUB_DOMAIN >> env_file
echo PRIMEHUB_PORT=$PRIMEHUB_PORT >> env_file
echo KC_SCHEME=$KC_SCHEME >> env_file
echo KC_DOMAIN=$KC_DOMAIN >> env_file
echo KC_PORT=$KC_PORT >> env_file
echo PH_USERNAME=$PH_USERNAME >> env_file
echo PH_PASSWORD=$PH_PASSWORD >> env_file
echo PRIMEHUB_STORAGE_CLASS=$PRIMEHUB_STORAGE_CLASS >> env_file
echo PRIMEHUB_MODE=$PRIMEHUB_MODE >> env_file

sudo ifconfig lo:0 inet ${BIND_ADDRESS} netmask 0xffffff00

# wait for docker in docker
echo "waiting for docker"
wait_for_docker

# install cluster
echo "create a cluster"
ci/dev-kind/setup-kind.sh

# install primehub
echo "install primehub"
ci/dev-kind/install-components.sh

# apply dev license
DEV_LICENSE=${DEV_LICENSE:-false}
if [ "$DEV_LICENSE" != "false" ]; then
  echo "Applying License for test."
  echo "$DEV_LICENSE" | base64 -d | kubectl apply -n hub -f -
  sleep 30
  wait_for_pod "primehub-graphql"
  wait_for_pod "primehub-console"
fi

# ensure rollout before testing
kubectl get deploy -n hub -o json | jq -r '.items[] | .metadata.name' | xargs -n1 kubectl rollout status -n hub deployment

# a bit more verbose
kubectl get pod  -n hub  -o=custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,MEMLIMITS:.spec.containers[*].resources.limits.memory,MEMREQUESTS:.spec.containers[*].resources.requests.memory,CPULIMITS:.spec.containers[*].resources.limits.cpu,CPUQUESTS:.spec.containers[*].resources.requests.cpu,STATUS:.status.phase'

# somehow the old rs of graphql server is very slow to get rid of
kubectl describe deploy -n hub primehub-graphql
sleep 60
kubectl describe deploy -n hub primehub-graphql
kubectl get pod  -n hub  -o=custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,MEMLIMITS:.spec.containers[*].resources.limits.memory,MEMREQUESTS:.spec.containers[*].resources.requests.memory,CPULIMITS:.spec.containers[*].resources.limits.cpu,CPUQUESTS:.spec.containers[*].resources.requests.cpu,STATUS:.status.phase'

# test
for filename in tests/*.sh; do echo $filename; $filename; done

# e2e test
export E2E_SUFFIX=$(openssl rand -hex 6)
source ~/.bashrc
mkdir -p e2e/screenshots e2e/webpages
tags="@released and not @ee and not @wip"
if [[ "${PRIMEHUB_MODE}" == "ee" ]]; then
  tags="@released and not @wip"
fi
~/project/node_modules/cucumber/bin/cucumber-js tests/features/ -f json:tests/report/cucumber_report.json --tags "$tags"