mkdir actions-runner && cd actions-runner

curl -o actions-runner-linux-x64-2.336.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.336.0/actions-runner-linux-x64-2.336.0.tar.gz

echo "04cf0be1aff4c3ec3554466c39124ca250e3effd8873bb7e8d68535aa9505d5d  actions-runner-linux-x64-2.336.0.tar.gz" | shasum -a 256 -c

tar xzf ./actions-runner-linux-x64-2.336.0.tar.gz

# GitHub에서 새 단기 runner 등록 토큰을 발급받아 환경 변수로 전달하세요.
./config.sh --url https://github.com/CodingHarang/OnMyWay --token "$RUNNER_REGISTRATION_TOKEN"

./run.sh

runs-on: self-hosted