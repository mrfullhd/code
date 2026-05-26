#!/bin/bash

# رنگ‌ها برای خروجی زیبا
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# فایل ورودی و خروجی
INPUT_FILE="proxy_socks_ip.txt"
WORKING_FILE="working_proxies.txt"
FAILED_FILE="failed_proxies.txt"

# بررسی وجود فایل
if [ ! -f "$INPUT_FILE" ]; then
    echo -e "${RED}Error: File $INPUT_FILE not found!${NC}"
    exit 1
fi

# پاک کردن فایل‌های قبلی
> "$WORKING_FILE"
> "$FAILED_FILE"

# تعداد کل پروکسی‌ها
total=$(grep -c ':' "$INPUT_FILE")
counter=1

echo -e "${YELLOW}=== Testing SOCKS5 Proxies ===${NC}"
echo "Total proxies: $total"
echo ""

# تابع تست پروکسی
test_proxy() {
    local proxy=$1
    local timeout=5
    
    # تست با curl (اتصال به گوگل)
    if curl -s -x socks5h://$proxy \
           --proxy-insecure \
           --connect-timeout $timeout \
           --max-time 10 \
           -I https://www.google.com > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# خواندن و تست خط به خط
while IFS= read -r proxy; do
    # حذف فاصله‌های خالی
    proxy=$(echo "$proxy" | xargs)
    
    # رد کردن خطوط خالی
    if [ -z "$proxy" ]; then
        continue
    fi
    
    echo -ne "[$counter/$total] Testing $proxy ... "
    
    if test_proxy "$proxy"; then
        echo -e "${GREEN}✓ WORKING${NC}"
        echo "$proxy" >> "$WORKING_FILE"
    else
        echo -e "${RED}✗ FAILED${NC}"
        echo "$proxy" >> "$FAILED_FILE"
    fi
    
    ((counter++))
done < "$INPUT_FILE"

# نمایش نتایج نهایی
echo ""
echo -e "${YELLOW}=== RESULTS ===${NC}"
echo -e "${GREEN}Working proxies: $(wc -l < $WORKING_FILE)${NC}"
echo -e "${RED}Failed proxies: $(wc -l < $FAILED_FILE)${NC}"
echo ""
echo -e "Working proxies saved to: ${GREEN}$WORKING_FILE${NC}"
echo -e "Failed proxies saved to: ${RED}$FAILED_FILE${NC}"
