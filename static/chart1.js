var ctx = document.getElementById('lineChart_current').getContext('2d');

// Dọn dẹp chuỗi string từ Python gửi sang (xóa dấu ngoặc vuông và nháy đơn)
var labels_1_raw = document.getElementById('labels_1').value;
var labels_1Array = labels_1_raw.replace(/[\[\]']/g, '').split(', ');

// Parse mảng số liệu
var data_1 = JSON.parse(document.getElementById('data_1').value);

var myChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: labels_1Array,
        datasets: [{
            label: 'Current Price ($)',
            data: data_1,
            backgroundColor: 'rgba(85,85,85, 0.2)',
            borderColor: 'rgb(41, 155, 99)',
            borderWidth: 2,
            tension: 0.1 // Làm cong mượt đường đồ thị
        }]
    },
    options: {
        responsive: true
    }
});