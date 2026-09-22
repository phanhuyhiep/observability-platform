#!/usr/bin/env bash
# scripts/start_port_forward.sh - Clean Port Forward Manager for Observability Platform

echo "🧹 [1/2] Đang dọn dẹp các tiến trình port-forward cũ..."
kill $(jobs -p) 2>/dev/null
pkill -9 -f "kubectl port-forward" 2>/dev/null
pkill -9 -f "30083" 2>/dev/null
pkill -9 -f "30082" 2>/dev/null
pkill -9 -f "4000" 2>/dev/null
pkill -9 -f "8888" 2>/dev/null
sleep 1

echo "🚀 [2/2] Đang mở kết nối Port-Forward ra toàn mạng (172.16.20.26)..."
nohup kubectl port-forward svc/frontend 8888:80 --address 0.0.0.0 > /dev/null 2>&1 &
nohup kubectl port-forward svc/grafana 4000:80 -n observability --address 0.0.0.0 > /dev/null 2>&1 &
nohup kubectl port-forward svc/rca-service 30082:8082 -n observability --address 0.0.0.0 > /dev/null 2>&1 &
nohup kubectl port-forward svc/ai-service 30083:8083 -n observability --address 0.0.0.0 > /dev/null 2>&1 &

sleep 2
echo ""
echo "================================================================="
echo "🎉 HỆ THỐNG ĐÃ MỞ CỔNG HOÀN TOÀN SẠCH SẼ & KHÔNG SPAM TERMINAL!"
echo "================================================================="
echo "   🛒 Online Boutique:     http://172.16.20.26:8888"
echo "   📊 Grafana Dashboard:  http://172.16.20.26:4000"
echo "   🔍 RCA Service API:    http://172.16.20.26:30082"
echo "   🤖 AI Copilot API/Web: http://172.16.20.26:30083"
echo "================================================================="
