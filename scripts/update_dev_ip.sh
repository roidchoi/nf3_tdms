#!/usr/bin/env zsh

# WSL 환경인지 검증
if grep -qE "(Microsoft|microsoft)" /proc/version 2>/dev/null; then
    # 윈도우 호스트의 실제 외부망 IPv4 추출 (루프백, WSL 가상 대역 및 API 대입 방지용 대역 제외)
    WIN_IP=$(powershell.exe -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { \$_.IPAddress -notlike '127.*' -and \$_.IPAddress -notlike '169.254.*' -and \$_.IPAddress -notlike '172.*' } | Select-Object -ExpandProperty IPAddress" 2>/dev/null | tr -d '\r' | head -n 1)
    
    ENV_PATH="/home/roid2/pjt/nf3/01_nf3_tdms/.env"
    if [ -f "$ENV_PATH" ]; then
        CURRENT_DEV_IP=$(grep -E "^DEV_IP=" "$ENV_PATH" | cut -d'=' -f2)
        
        if [ -n "$WIN_IP" ] && [ "$CURRENT_DEV_IP" != "$WIN_IP" ]; then
            echo "🔄 WSL2 Windows Host IP change detected: $CURRENT_DEV_IP -> $WIN_IP"
            # .env 내 DEV_IP 필드 값 갱신
            sed -i "s/^DEV_IP=.*/DEV_IP=$WIN_IP/" "$ENV_PATH"
            echo "✅ Updated DEV_IP in .env to $WIN_IP"
            export DEV_IP="$WIN_IP"
        else
            export DEV_IP="$CURRENT_DEV_IP"
        fi
    fi
fi
